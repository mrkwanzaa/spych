from spych.utils import Notify
from spych.cli import CliColor, CliSpinner, CliPrinter
from typing import Optional
import time


class BaseResponder(Notify):
    def __init__(
        self,
        spych_object: "Spych",
        listen_duration: int | float = 5,
        name: Optional[str] = None,
        interactive: bool = True,
    ) -> None:
        """
        Usage:

        - Base class for all responders. Handles the listen-transcribe-respond cycle,
          provides a consistent interface for subclasses to implement, and includes
          a rich terminal UI: animated spinner, live tool-call streaming, and an
          optional interactive clarification prompt.

        - Subclasses only need to implement `respond(user_input: str) -> str`.
          All CLI chrome (spinner, dividers, timing, response box) is handled here.

        - Public helper methods are available inside `respond()` for common
          UI needs without importing CLI internals:
            - `self.emit_tool_event(name, status)`  — show a tool-call line
            - `self.update_spinner(message)`         — change the spinner label
            - `self.pause_spinner()`                 — stop spinner (e.g. before printing)
            - `self.resume_spinner(message)`         — restart spinner after a pause
            - `self.print_info(message, color)`      — print a styled info line

        Requires:

        - `spych_object`:
            - Type: Spych
            - What: An initialized Spych instance used to record and transcribe audio
              after the wake word is detected

        Optional:

        - `listen_duration`:
            - Type: int | float
            - What: The number of seconds to listen for after the wake word is detected
            - Default: 5

        - `name`:
            - Type: str
            - What: A custom name for the responder to use in printed messages
            - Default: The class name of the responder (e.g., "Ollama")

        - `interactive`:
            - Type: bool
            - What: When True, a pre-flight prompt asks whether any clarification is
              needed before the main call is made; the user can type a reply in
              the terminal
            - Default: True

        Notes:

        - Subclasses must implement the `respond` method
        - The `__call__` method orchestrates the full listen -> transcribe -> respond
          cycle; subclasses only need to handle the response logic
        """
        self.spych_object = spych_object
        self.listen_duration = listen_duration
        self.name = name if name else self.__class__.__name__
        self.interactive = interactive
        self._spinner = CliSpinner()
        self._enriched_input: str = ""
        self._start_time: float = 0.0

    # ------------------------------------------------------------------ #
    #  Public helper API — safe to call from inside respond()             #
    # ------------------------------------------------------------------ #

    def emit_tool_event(self, tool_name: str, status: str = "running") -> None:
        """
        Usage:

        - Emit a styled tool-call line (⚙ running / ✓ done) to the terminal.
          Automatically pauses and resumes the spinner so output is not garbled.
          Call this from inside `respond()` whenever your responder invokes an
          external tool or sub-process you want to surface to the user.

        Requires:

        - `tool_name`:
            - Type: str
            - What: Short label for the tool being invoked (e.g. "web_search")

        Optional:

        - `status`:
            - Type: str  ("running" | "done")
            - What: Controls the icon and color of the event line
            - Default: "running"
        """
        self._spinner.stop()
        CliPrinter.tool_event(tool_name, status)
        if status == "running":
            self._spinner.start(f"Running {tool_name}")
        else:
            self._spinner.start(f"{self.name} is thinking")

    def wait_for_next_wake_word(self):
        CliPrinter.divider("─", 60, CliColor.GRAY)
        self.start_spinner(f"Waiting for wake word")

    def start_spinner(self, message: str) -> None:
        """Start the spinner with a custom message."""
        self._spinner.start(message)

    def update_spinner(self, message: str) -> None:
        """
        Usage:

        - Update the spinner's status message without stopping it.
          Useful for multi-stage work inside `respond()`.

        Requires:

        - `message`:
            - Type: str
            - What: The new label shown next to the spinner
        """
        self._spinner.update(message)

    def pause_spinner(self) -> None:
        """
        Usage:

        - Stop the spinner and clear the line so you can print freely.
          Call `resume_spinner()` when done printing.
        """
        self._spinner.stop()

    def resume_spinner(self, message: str | None = None) -> None:
        """
        Usage:

        - Restart the spinner after a `pause_spinner()` call.

        Optional:

        - `message`:
            - Type: str
            - What: Spinner label to use; defaults to "<name> is thinking"
        """
        self._spinner.start(message or f"{self.name} is thinking")

    def print_info(self, message: str, color: str = CliColor.CYAN) -> None:
        """
        Usage:

        - Print a styled informational line from inside `respond()`.
          The spinner is paused automatically and resumed afterwards so
          the output line is never overwritten.

        Requires:

        - `message`:
            - Type: str
            - What: The message to display

        Optional:

        - `color`:
            - Type: str (CliColor constant)
            - What: ANSI color for the info icon
            - Default: CliColor.CYAN
        """
        self._spinner.stop()
        CliPrinter.info(message, color)
        self._spinner.start(f"{self.name} is thinking")

    # ------------------------------------------------------------------ #
    #  Extension hooks — override in subclasses for custom behaviour      #
    # ------------------------------------------------------------------ #

    def respond(self, user_input: str) -> str:
        """
        Usage:

        - Called with the transcribed (and optionally clarified) user input.
          Must return a response string. All CLI chrome is handled by the base
          class; this method only needs to produce the response.

        - Use the public helper methods for UI feedback inside this method:

            self.emit_tool_event("my_tool")          # ⚙ tool: my_tool
            self.emit_tool_event("my_tool", "done")  # ✓ tool: my_tool
            self.update_spinner("Fetching data")
            self.print_info("Found 3 results")
            self.pause_spinner()
            print("  anything you like")
            self.resume_spinner()

        Requires:

        - `user_input`:
            - Type: str
            - What: The transcribed text from the user's audio input

        Returns:

        - `response`:
            - Type: str
            - What: The response string to print to the terminal
        """
        raise NotImplementedError("Subclasses must implement the `respond` method")

    def on_before_respond(self, user_input: str) -> None:
        """
        Usage:

        - Optional lifecycle hook called immediately before `respond()`.
          Override for setup, logging, or any pre-flight work.
          The spinner is already running when this is called.

        Requires:

        - `user_input`:
            - Type: str
            - What: The enriched transcribed input (after optional clarification)
        """

    def on_after_respond(self, user_input: str, response: str) -> None:
        """
        Usage:

        - Optional lifecycle hook called immediately after `respond()` returns,
          before the response box is printed. Override for logging, analytics,
          caching, or post-processing.

        Requires:

        - `user_input`:
            - Type: str
            - What: The enriched transcribed input passed to `respond()`

        - `response`:
            - Type: str
            - What: The raw string returned by `respond()`
        """

    def clarify(self, user_input: str) -> str:
        """
        Usage:

        - Override this to use a clarification backend (e.g. an LLM) to check whether the 
        transcribed input needs clarification before executing the main response logic. 
        The method should return either the original input (if no clarification is needed) 
        or the original input appended with any additional context from the user.

        Requires:

        - `user_input`:
            - Type: str
            - What: The raw transcribed user input

        Returns:

        - `updated_user_input`:
            - Type: str
            - What: The original input, optionally appended with clarification context
        """
        return user_input  # By default, no clarification is done; just return the original input

    # ------------------------------------------------------------------ #
    #  Orchestration — not intended for override; use the hooks above     #
    # ------------------------------------------------------------------ #

    def on_listen_start(self) -> None:
        # Start a spinner immediately to indicate we're processing the wake event and listening;
        # this also gives a visual cue that the wake was detected successfully and the responder is active
        self.update_spinner(f"{self.name} is listening for {self.listen_duration}s")

    def on_user_input(self, user_input: str) -> None:
        CliPrinter.label("USER:", user_input)

        if self.interactive:
            self._spinner.start("Checking for clarifications")
            self._spinner.stop()
            self._enriched_input = self.clarify(user_input)
        else:
            self._enriched_input = user_input

        self._start_time = time.time()
        self._spinner.start(f"{self.name} is thinking")

    def on_response(self, response: str) -> None:
        elapsed = time.time() - self._start_time
        self._spinner.stop()
        if response:
            CliPrinter.print_response(self.name, response)
            print(
                f"\n{CliColor.GREEN}✓{CliColor.RESET}  {CliColor.DIM}Done in {elapsed:.1f}s{CliColor.RESET}"
            )
        else:
            print(f"{CliColor.RED}✗  No response received.{CliColor.RESET}")

    def on_listen_end(self) -> None:
        self.pause_spinner()

    def __call__(self) -> str:
        """
        Usage:

        - Executes one full wake-triggered cycle: listens, transcribes, responds,
          and prints.

        Returns:

        - `response`:
            - Type: str
            - What: The response string returned by `respond`
        """
        self.on_listen_start()
        user_input = self.spych_object.listen(duration=self.listen_duration)
        self.on_listen_end()
        self.on_user_input(user_input)
        try:
            self.on_before_respond(self._enriched_input)
            response = self.respond(self._enriched_input)
            self.on_after_respond(self._enriched_input, response)
        except Exception as exc:
            self._spinner.stop()
            print(f"  {CliColor.RED}✗  Error: {exc}{CliColor.RESET}\n")
            return ""
        self.on_response(response)
        self.wait_for_next_wake_word()
        return response
    
    def ready_message(
        self,
        wake_words: list[str],
        terminate_words: list[str],
    ) -> None:
        """
        Formats and prints the ready message when the responder is initialized, showing the wake words, terminate words, and interactive status.

        Requires:

        - `wake_words`:
            - Type: list[str]
            - What: List of wake words that trigger the responder

        - `terminate_words`:
            - Type: list[str]
            - What: List of words that can be spoken to terminate the responder
        """
        CliPrinter.header(self.name, "")
        print(
            f"  {CliColor.GRAY}Wake words  : {CliColor.WHITE}{', '.join(wake_words)}{CliColor.RESET}\n"
            f"  {CliColor.GRAY}Terminate   : {CliColor.WHITE}{', '.join(terminate_words)}{CliColor.RESET}\n"
            f"  {CliColor.GRAY}Interactive : {CliColor.WHITE}{self.interactive}{CliColor.RESET}\n"
        )
        self.wait_for_next_wake_word()