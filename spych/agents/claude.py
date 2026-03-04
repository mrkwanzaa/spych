from spych.core import Spych
from spych.wake import SpychWake
from spych.cli import CliPrinter, CliColor
from spych.responders import BaseResponder
import threading, subprocess, json, re


class LocalClaudeCodeCLIResponder(BaseResponder):
    def __init__(
        self,
        spych_object: "Spych",
        continue_conversation: bool = True,
        listen_duration: int | float = 5,
        name: str | None = "Claude Code",
        interactive: bool = True,
    ) -> None:
        """
        Usage:

        - A responder that pipes transcribed audio into the Claude Code CLI (`claude -p`)
          and returns the final response, waiting for all tool calls to complete.
          Features a live terminal spinner, streamed tool-call events, and an
          optional interactive clarification prompt when the query is ambiguous.

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

        - `interactive`:
            - Type: bool
            - What: When True, Claude may ask a short clarifying question before
              executing if the request is ambiguous; the user types a reply in
              the terminal
            - Default: True

        Notes:

        - Uses `--output-format stream-jsonl` (with json fallback) so tool calls
          are shown live as they execute
        - Claude Code must be installed and authenticated before use
        - Clarification is handled by BaseResponder; do NOT call clarify() inside respond()
        """
        super().__init__(
            spych_object=spych_object,
            listen_duration=listen_duration,
            name=name,
            interactive=interactive,
        )
        self.continue_conversation = continue_conversation
        self.first_call = True
        self._first_call_lock = threading.Lock()

    def clarify(self, user_input: str) -> str:
        """
        Usage:

        - Asks Claude Code CLI whether the request needs clarification before
          executing.

        Requires:

        - `user_input`:
            - Type: str
            - What: The raw transcribed user input

        Returns:

        - `updated_user_input`:
            - Type: str
            - What: The original input, optionally appended with clarification context
        """
        preflight_prompt = (
            'The user said: "{input}"\n\n'
            "If this request is clear and complete, reply with exactly: CLEAR\n"
            "If you need ONE short clarifying question to do it well, reply with "
            "just that question and nothing else."
        ).format(input=user_input)

        try:
            result = subprocess.run(
                ["claude", "-p", preflight_prompt, "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=60
            )
        except subprocess.TimeoutExpired:
            print(
                f"\n  {CliColor.YELLOW}⚠ Clarification check timed out. "
                f"Proceeding with original input.{CliColor.RESET}\n"
            )
            return user_input
        except Exception as e:
            print(
                f"\n  {CliColor.YELLOW}⚠ Clarification check failed "
                f"(error: {e}). "
                f"Proceeding with original input.{CliColor.RESET}\n"
            )
            return user_input

        if result.returncode != 0:
            err = result.stderr.strip() or "unknown error"
            print(
                f"\n  {CliColor.YELLOW}⚠ Clarification check failed "
                f"(claude CLI returned {result.returncode}: {err}). "
                f"Proceeding with original input.{CliColor.RESET}\n"
            )
            return user_input

        # Parse the JSON response
        try:
            parsed_response = json.loads(result.stdout)
            answer = parsed_response.get("result", "CLEAR").strip()
        except json.JSONDecodeError:
            # If JSON parsing fails, use raw stdout
            answer = result.stdout.strip()

        # If no clarification is needed, return original input
        if answer.upper().startswith("CLEAR") or not answer:
            return user_input

        # Ask for clarification and append to input
        print(
            f"\n  {CliColor.YELLOW}{CliColor.BOLD}? Clarification needed{CliColor.RESET}\n"
            f"  {CliColor.WHITE}{answer}{CliColor.RESET}"
        )

        try:
            reply = input(f"  {CliColor.CYAN}Your answer:{CliColor.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            reply = ""

        if reply:
            return f"{user_input} — Additional context: {reply}"
        return user_input
    
    def run_claude_streaming(
        self,
        cmd: list[str],
    ) -> str:
        """
        Runs `claude` with --output-format stream-jsonl (if available) or json,
        prints tool-call events live, and returns the final result string.
        """
        stream_cmd = [c for c in cmd]
        try:
            idx = stream_cmd.index("json")
            stream_cmd[idx] = "stream-jsonl"
        except ValueError:
            pass

        process = subprocess.Popen(
            stream_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        final_result = ""
        seen_tools: set[str] = set()
        tool_line_re = re.compile(r'"tool_name"\s*:\s*"([^"]+)"')

        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    tool_name = obj.get("tool_name")
                    if tool_name and tool_name not in seen_tools:
                        seen_tools.add(tool_name)
                        self.spinner.stop()
                        CliPrinter.tool_event(tool_name, "running")
                        self.spinner.start(f"Running {tool_name}")

                    if obj.get("type") == "result" or "result" in obj:
                        candidate = obj.get("result", "")
                        if candidate:
                            final_result = candidate
                            self.spinner.update("Finishing up")
                continue
            except json.JSONDecodeError:
                pass

            tool_match = tool_line_re.search(line)
            if tool_match:
                tool_name = tool_match.group(1)
                if tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    self.spinner.stop()
                    CliPrinter.tool_event(tool_name, "running")
                    self.spinner.start(f"Running {tool_name}")

        process.wait()

        for tool in seen_tools:
            CliPrinter.tool_event(tool, "done")

        if not final_result and process.returncode != 0:
            fallback = subprocess.run(cmd, capture_output=True, text=True)
            try:
                final_result = json.loads(fallback.stdout).get("result", "").strip()
            except json.JSONDecodeError:
                final_result = fallback.stdout.strip()

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

        cmd = ["claude", "-p", user_input, "--output-format", "json"]
        if self.continue_conversation and not is_first:
            cmd.append("--continue")

        response = self.run_claude_streaming(cmd)
        return response


def claude_code_cli(
    wake_words: list[str] = ["claude"],
    terminate_words: list[str] = ["terminate"],
    listen_duration: int | float = 5,
    continue_conversation: bool = True,
    interactive: bool = True,
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
        - Default: ["claude"]
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

    - `interactive`:
        - Type: bool
        - What: When True, Claude may ask a short clarifying question before
          executing if the request is ambiguous; the user types a reply in
          the terminal
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
        interactive=interactive,
        listen_duration=listen_duration,
    )

    # SpychWake Object
    spych_wake_kwargs = {
        "whisper_model": "base.en", 
        "wake_word_map": {word: responder for word in wake_words},
        "terminate_words": terminate_words,
        **(spych_wake_kwargs or {})
    }
    spych_wake_object = SpychWake(**spych_wake_kwargs)

    # Fire ready message and start wake listener
    responder.ready_message(wake_words, terminate_words)
    spych_wake_object.start()