import openai
import streamlit as st
import os
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.search.documents.models import Vector
from azure.core.credentials import AzureKeyCredential
from PIL import Image

load_dotenv()

openai.api_type = os.environ.get("AZURE_OPENAI_TYPE")
openai.api_base = os.environ.get("AZURE_OPENAI_ENDPOINT")
openai.api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
openai.api_key = os.environ.get("AZURE_OPENAI_API_KEY")
model: str = os.environ.get("AZURE_OPENAI_MODEL_NAME")

vector_store_address: str = os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
vector_store_key: str = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
model_embed: str = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYED_MODEL")
index_name: str = "lightfoot-vector-index"
credential_search = AzureKeyCredential(vector_store_key)

search_client = SearchClient(
        endpoint=vector_store_address,
        index_name=index_name,
        credential=credential_search,
    )


with st.sidebar:
    #st.button("New Chat", type="primary")
    st.write("💬 Start a new Chat")
    if st.button('New Chat'):
        # Delete all the items in Session state
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

st.title("Chat with a Gordon Bot")
st.write("Idea here is you engage in a chat with :red[Gordon] about an email you need to send.  He will prompt you for information about your email.  When you are done chatting hit the :blue[Done Chatting] button and your email will be generated")

st.divider()

###     file operations

def save_file(filepath, content):
    with open(filepath, 'w', encoding='utf-8') as outfile:
        outfile.write(content)

def open_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as infile:
        return infile.read()
    
def chatbot(conversation, engine=model, temperature=0, max_tokens=2000):
    max_retry = 7
    retry = 0    

    while True:
        try:
            response = openai.ChatCompletion.create(engine=engine, messages=conversation, temperature=temperature, max_tokens=max_tokens)
            text = response['choices'][0]['message']['content']
            
            return text, response['usage']['total_tokens']
        except Exception as oops:
            print(f'\n\nError communicating with OpenAI: "{oops}"')
            exit(5)

# Function to generate embeddings for title and content fields, also used for query embeddings
def generate_embeddings(text):
    response = openai.Embedding.create(
        input=text, engine="text-embedding-ada-002")
    embeddings = response['data'][0]['embedding']
    return embeddings

def search_api(query: str) -> str:  
    results = []
    search_client = SearchClient(vector_store_address, index_name, credential_search)  
    vector = Vector(value=generate_embeddings(query), k=5, fields="contentVector")  

    r = search_client.search(  
        search_text=query,  
        vectors=[vector],
        select=["content", "title"],
        top=5
    )  
    for doc in r:
        results.append(f"[CITATIONS:  {doc['title']}]" + "\n" + (doc['content']))
    #print("\n".join(results))
    return ("\n".join(results))

# use this for capturing an easy to read transcript of the chat conversation
all_messages = list()

if "messages_chatbot" not in st.session_state:
    st.session_state["messages_chatbot"] = [{"role": "assistant", "content": "Tell me what you want to say in your email?"}]

# display the flow of chat bubbles between user and assistant
for msg in st.session_state.messages_chatbot:
    if msg["role"] == "user":
        st.chat_message(msg["role"], avatar=Image.open('../images/User.png')).write(msg["content"])
        all_messages.append('USER: %s' % msg["content"])
    elif msg["role"] == "assistant":
        st.chat_message(msg["role"], avatar=Image.open('../images/Gordon.png')).write(msg["content"])
        all_messages.append('GORDON BOT: %s' % msg["content"])

if prompt := st.chat_input():

    #print(search_api(prompt))
    # set the system message and user message into the session state
    st.session_state.messages_chatbot.append({"role": "system", "content": open_file('../system_01_intake.md')})
    st.session_state.messages_chatbot.append({"role": "user", "content": prompt})

    # now fill the user chat bubble and append to all_messages - this is used to make an easy to read conversation
    st.chat_message("user", avatar=Image.open('../images/User.png')).write(prompt)

    # now call the openai chat completion and get the response into a string
    #msg, tokens = chatbot(st.session_state.messages_chatbot)
    response = openai.ChatCompletion.create(engine=model, temperature=0.0, max_tokens=1200, messages=st.session_state.messages_chatbot)
    msg = response.choices[0].message

    # add the response from the llm to the session state
    st.session_state.messages_chatbot.append(msg)

    # now fill the assistant chat bubble and append to all_messages - this is used to make an easy to read conversation
    st.chat_message("assistant", avatar=Image.open('../images/Gordon.png')).write(msg.content)

st.divider()

with st.form("send_intake"):
        st.write("Click to start generating notes, suggestions and actions")
        submitted = st.form_submit_button("Done chatting ..... Write my email!")
        if submitted:
            conversation = list()
            conversation.append({'role': 'system', 'content': open_file('../system_02_prepare_notes.md')})
            text_block = '\n\n'.join(all_messages)
            chat_log = '<<BEGIN CHAT>>\n\n%s\n\n<<END CHAT>>' % text_block
            with st.expander("💬 Chat Log"):
                st.write(chat_log)
            conversation.append({'role': 'user', 'content': chat_log})
            with st.spinner('Creating notes...'):
                notes, tokens = chatbot(conversation)
            with st.expander("📖 Notes"):
                st.write(notes)

            #print('\n\nGenerating Hypothesis Report')
            conversation = list()
            conversation.append({'role': 'system', 'content': open_file('../system_03_email.md').replace('<<CONTEXT>>', search_api(notes))})
            conversation.append({'role': 'user', 'content': notes})
            with st.spinner('Creating email a la Gordon...'):
                email, tokens = chatbot(conversation)
            with st.expander("📩 Email"):
                st.write(email)