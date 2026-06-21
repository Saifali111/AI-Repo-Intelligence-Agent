import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

client = Client()

# simple test trace
from langsmith import traceable

@traceable(name="test_trace")
def test_function(input_text):
    return f"Processed: {input_text}"

result = test_function("hello devpulse")
print(result)
print("Check smith.langchain.com for the trace under project 'devpulse'")