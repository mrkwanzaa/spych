from spych.wake import SpychWake
from spych.core import Spych
from spych.responders import BaseResponder
import subprocess, json

class LocalClaudeCodeCLIResponder(BaseResponder):
    def __init__(
        self, spych_object, continue_conversation=True, listen_duration=5, name="Claude Code"
    ):
        """
        Usage:

        - A responder that pipes transcribed audio into the Claude Code CLI (`claude -p`)
          and returns the final response, waiting for all tool calls to complete

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

        - Uses `--output-format json` so the subprocess blocks until Claude has finished
          all tool calls and returns only the final result, not intermediate tool call XML
        - Claude Code must be installed and authenticated before use
        """
        super().__init__(
            spych_object=spych_object, listen_duration=listen_duration, name=name
        )
        self.continue_conversation = continue_conversation
        self.first_call = True

    def respond(self, user_input):
        """
        Usage:

        - Pipes the transcribed user input into `claude -p` and returns the final response
          after all tool calls have completed

        Requires:

        - `user_input`:
            - Type: str
            - What: The transcribed text from the user's audio input

        Returns:

        - `response`:
            - Type: str
            - What: The final response string from Claude Code
        """
        cmd = ["claude", "-p", user_input, "--output-format", "json"]
        if self.continue_conversation and not self.first_call:
            cmd.append("--continue")
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.first_call = False
        try:
            return json.loads(result.stdout).get("result", "").strip()
        except json.JSONDecodeError:
            return result.stdout.strip()

def claude_code_cli(
    whisper_device: str = "cpu",
    wake_words: list[str] = ["claude"],
    terminate_words: list[str] = ["terminate"],
    listen_duration: int | float = 5,
    continue_conversation: bool = True,
) -> None:
    """
    Usage:

    - Starts a wake word listener that pipes detected speech into the Claude Code CLI

    Optional:

    - `whisper_device`:
        - Type: str
        - What: The device to run the whisper models on
        - Default: "cpu"
        - Note: Use "cuda" for GPU acceleration if available

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
    """
    spych_object = Spych(
        whisper_model="base.en",
        whisper_device=whisper_device
    )
    responder = LocalClaudeCodeCLIResponder(
        spych_object,
        continue_conversation=continue_conversation,
        listen_duration=listen_duration,
    )
    wake_word_map = {word: responder for word in wake_words}
    wake_object = SpychWake(
        wake_word_map=wake_word_map,
        whisper_model="tiny.en",
        whisper_device=whisper_device,
        terminate_words=terminate_words,
    )
    wake_object.start()