from groq import Groq

client = Groq(
    api_key="__"
)

completion = client.chat.completions.create(
    # model="qwen/qwen3-32b",

    model="llama-3.1-8b-instant",
    messages=[
        {
            "role": "system",
            "content": "Tu és um assistente especializado em explicar código Python de forma clara e técnica."
        },
        {
            "role": "user",
            "content": "Explica-me o que é um decorator"
        }
    ]
)

print(completion.choices[0].message.content)