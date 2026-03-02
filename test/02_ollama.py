from spych.agents import ollama

print("Starting Ollama agent")
print("Listening for wake word 'llama'...")
ollama(model="llama3.2:latest")
