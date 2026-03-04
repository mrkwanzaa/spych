from spych.core import Spych
from spych.wake import SpychWake
from spych.cli import CliPrinter
from spych.responders import BaseResponder
import threading, subprocess, json, time


class LocalClaudeCodeCLIResponder(BaseResponder):
    def __init__(
        self,
        spych_object: "Spych",
        continue_conversation: bool = True,
        listen_duration: int | float = 5,
        name: str | None = "Claude Code",
    ) -> None:
        """
        Usage:

        - A responder that pipes transcribed audio into the Claude Code CLI (`claude -p`)
          and returns the final response, waiting for all tool calls to complete.
          Features a live terminal spinner and streamed tool-call events

        Requires:

        - `spych_object`:
            - Type: Spych
            - What: An initialized Spych instance used to record and transcribe audio

        Optional:

        - `continue_conversation`:
            - Type: bool
            - What: Whether to pass `--continue` to reuse the most recent session
            - Default: True

        - `listen_duration`:
            - Type: int | float
            - What: The number of seconds to listen for after the wake word is detected
            - Default: 5

        - `name`:
            - Type: str
            - What: A custom name for the responder to use in printed messages
            - Default: "Claude Code"

        Notes:

        - Uses `--output-format stream-jsonl` so tool calls are shown live as they execute
        - Claude Code must be installed and authenticated before use
        """
        super().__init__(
            spych_object=spych_object,
            listen_duration=listen_duration,
            name=name,
        )
        self.continue_conversation = continue_conversation
        self.first_call = True
        self._first_call_lock = threading.Lock()

    def run_claude_streaming(
        self,
        cmd: list[str],
    ) -> str:
        """
        Usage:

        - Runs `claude` with --output-format stream-jsonl, prints tool-call events
          live with elapsed time, and returns the final result string.

        Requires:

        - `cmd`:
            - Type: list[str]
            - What: The full command to run, including all flags

        Returns:

        - `final_result`:
            - Type: str
            - What: The final response string from Claude Code
        """
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        final_result = ""
        # Maps tool_use id -> (tool_name, start_time)
        seen_tools: dict[str, tuple[str, float]] = {}

        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    msg_type = obj.get("type")

                    # Tool is starting
                    if msg_type == "tool_use":
                        tool_id = obj.get("id", "")
                        tool_name = obj.get("name", "unknown tool")
                        if tool_id not in seen_tools:
                            seen_tools[tool_id] = (tool_name, time.time())
                            self.spinner.stop()
                            self.tool_event(tool_name, "running", is_running=True)
                            self.spinner.start()

                    # Tool has finished
                    elif msg_type == "tool_result":
                        tool_use_id = obj.get("tool_use_id", "")
                        if tool_use_id in seen_tools:
                            tool_name, start = seen_tools[tool_use_id]
                            elapsed = f"{time.time() - start:.2f}s"
                            self.spinner.stop()
                            self.tool_event(tool_name, "done", is_running=False, elapsed=elapsed)
                            self.spinner.start()

                    # Final answer
                    elif msg_type == "result":
                        candidate = obj.get("result", "")
                        if candidate:
                            final_result = candidate

                continue
            except json.JSONDecodeError:
                pass

        process.wait()

        if not final_result and process.returncode != 0:
            err = process.stderr.read()
            fallback = subprocess.run(
                [c.replace("stream-jsonl", "json") for c in cmd],
                capture_output=True,
                text=True,
            )
            try:
                final_result = json.loads(fallback.stdout).get("result", "").strip()
            except json.JSONDecodeError:
                final_result = fallback.stdout.strip() or err.strip()

        return final_result.strip()

    def respond(self, user_input: str) -> str:
        """
        Usage:

        - Pipes the transcribed (and optionally clarified) user input into
          `claude -p` and returns the final response string.
          The spinner is already running when this is called (started by
          BaseResponder.on_user_input); do not start it again here.

        Requires:

        - `user_input`:
            - Type: str
            - What: The enriched transcribed text (may include clarification context)

        Returns:

        - `response`:
            - Type: str
            - What: The final response string from Claude Code
        """
        with self._first_call_lock:
            is_first = self.first_call
            self.first_call = False

        cmd = ["claude", "-p", user_input, "--output-format", "stream-jsonl"]
        if self.continue_conversation and not is_first:
            cmd.append("--continue")

        response = self.run_claude_streaming(cmd)
        return response


def claude_code_cli(
    wake_words: list[str] = ["claude", "clod", "cloud", "clawed"],
    terminate_words: list[str] = ["terminate"],
    listen_duration: int | float = 5,
    continue_conversation: bool = True,
    spych_kwargs: dict[str, any] | None = None,
    spych_wake_kwargs: dict[str, any] | None = None,
) -> None:
    """
    Usage:

    - Starts a wake word listener that pipes detected speech into the Claude Code CLI

    Optional:

    - `wake_words`:
        - Type: list[str]
        - What: A list of wake words that each trigger the Claude Code CLI responder
        - Default: ["claude", "clod", "cloud", "clawed"]
        - Note: All wake words in this list map to the same LocalClaudeCodeCLIResponder
          instance, sharing conversation history across triggers

    - `terminate_words`:
        - Type: list[str]
        - What: A list of terminate words that each trigger the termination of the Claude Code CLI responder
        - Default: ["terminate"]
        - Note: All terminate words in this list map to the same LocalClaudeCodeCLIResponder
          instance, sharing conversation history across triggers

    - `listen_duration`:
        - Type: int | float
        - What: The number of seconds to listen for after the wake word is detected
        - Default: 5

    - `continue_conversation`:
        - Type: bool
        - What: Whether to pass `--continue` to reuse the most recent session in Claude CLI
        - Default: True

    - `spych_kwargs`:
        - Type: dict
        - What: Additional keyword arguments to pass to the Spych constructor
        - Default: None

    - `spych_wake_kwargs`:
        - Type: dict
        - What: Additional keyword arguments to pass to the SpychWake constructor
        - Default: None
    """
    # Spych Object
    spych_kwargs = {"whisper_model": "base.en", **(spych_kwargs or {})}
    spych_object = Spych(**spych_kwargs)

    # Responder Object
    responder = LocalClaudeCodeCLIResponder(
        spych_object=spych_object,
        continue_conversation=continue_conversation,
        listen_duration=listen_duration,
    )

    # SpychWake Object
    spych_wake_kwargs = {
        "whisper_model": "base.en",
        "on_terminate": responder.on_terminate,
        "wake_word_map": {word: responder for word in wake_words},
        "terminate_words": terminate_words,
        **(spych_wake_kwargs or {})
    }
    spych_wake_object = SpychWake(**spych_wake_kwargs)

    # Fire ready message and start wake listener
    responder.ready_message(wake_words, terminate_words)
    spych_wake_object.start()