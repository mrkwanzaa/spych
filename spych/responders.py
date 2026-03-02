from spych.utils import Notify


class BaseResponder(Notify):
    def __init__(self, spych_object, listen_duration=5, name: str = None):
        """
        Usage:

        - Base class for all responders. Handles the listen-transcribe-respond cycle
          and provides a consistent interface for subclasses to implement

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

        Notes:

        - Subclasses must implement the `respond` method
        - The `__call__` method orchestrates the full listen -> transcribe -> respond cycle
          and handles printing; subclasses only need to handle the response logic
        """
        self.spych_object = spych_object
        self.listen_duration = listen_duration
        self.name = name if name else self.__class__.__name__

    def respond(self, user_input):
        """
        Usage:

        - Called with the transcribed user input and expected to return a response string
        - Must be implemented by all subclasses

        Requires:

        - `user_input`:
            - Type: str
            - What: The transcribed text from the user's audio input

        Returns:

        - `response`:
            - Type: str
            - What: The response string to print and return to the caller
        """
        raise NotImplementedError(
            "Subclasses must implement the `respond` method"
        )

    def on_listen_start(self):
        """
        Usage:

        - Returns a string message to print when starting to listen for user input
        - Can be overridden by subclasses for custom messages
        - prints a default message indicating how long it will listen for instructions

        Returns:

        - None (default behavior does nothing)
        """
        print(f"Waiting {self.listen_duration}s for instructions...")
        return None

    def on_user_input(self, user_input):
        """
        Usage:

        - Hook method that is called with the transcribed user input before generating a response
        - Can be overridden by subclasses to perform actions based on the user input
        - prints the user input by default for visibility, but can be customized or overridden as needed

        Requires:

        - `user_input`:
            - Type: str
            - What: The transcribed user input

        Returns:

        - `None` (default behavior does nothing)
        """
        print("You: ", user_input)

    def on_response(self, response):
        """
        Usage:

        - Hook method that is called with the generated response before printing
        - Can be overridden by subclasses to perform actions based on the response
        - prints the response by default for visibility, but can be customized or overridden as needed

        Requires:

        - `response`:
            - Type: str
            - What: The generated response string

        Returns:
        - `None` (default behavior does nothing)
        """
        print(f"{self.name}: ", response)

    def on_listen_end(self):
        """
        Usage:

        - Returns a string message to print when finished listening for user input
        - Can be overridden by subclasses for custom messages

        Returns:

        - `message`:
            - Type: str
            - What: The message to print when finished listening
        """
        return print("=" * 20)

    def __call__(self):
        """
        Usage:

        - Executes one full wake-triggered cycle: listens, transcribes, responds, and prints

        Returns:

        - `response`:
            - Type: str
            - What: The response string returned by `respond`
        """
        self.on_listen_start()
        user_input = self.spych_object.listen(duration=self.listen_duration)
        self.on_user_input(user_input)
        response = self.respond(user_input)
        self.on_response(response)
        self.on_listen_end()
        return response
