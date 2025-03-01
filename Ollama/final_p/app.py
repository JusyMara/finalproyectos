from flask import Flask, request, jsonify
from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.document_loaders import PDFPlumberLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma  # Actualización para usar el nuevo Chroma
from langchain.prompts import ChatPromptTemplate
import smtplib
import os
from dotenv import load_dotenv, dotenv_values
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart



app = Flask(__name__)

if os.path.exists("final_p/.env"):
    load_dotenv(override=True)
    config = dotenv_values(".env")
    
email_sender = os.getenv("EMAIL_SENDER")
email_password = os.getenv("EMAIL_PASSWORD")
smtp_server = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT"))

# Instancia de Llama 3.2 usando Ollamap
llm = Ollama(model="llama3.2")

# Instancia de embeddings de Llama 3.2
embedding = OllamaEmbeddings(model="jina/jina-embeddings-v2-base-es")

# Text splitter para dividir el contenido de los PDF en chunks manejables
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1024, chunk_overlap=80
)

# Prompt para dar contexto al asistente

# Función para enviar correo electrónico
def send_email(to_email, subject, body):
    print("exec")

    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_sender, email_password)
            server.send_message(msg)
        print("Test email sent successfully!")
    except Exception as e:
        print(f"Error sending test email: {str(e)}")
        
# Definición de las funciones disponibles para el modelo
    
functions = [
    {
        "name": "send_email",
        "description": "Envía un correo electrónico al paciente",
        "parameters": {
            "type": "object",
            "properties": {
                "to_email": {
                    "type": "string",
                    "description": "La dirección de correo electrónico del destinatario"
                },
                "subject": {
                    "type": "string",
                    "description": "El asunto del correo electrónico"
                },
                "body": {
                    "type": "string",
                    "description": "El cuerpo del correo electrónico"
                }
            },
            "required": ["to_email", "subject", "body"]
        }
    }
]
    
    
raw_prompt  = """
Eres un asistente llamado Leo, un excelente psicólogo profesional, ayudas a pacientes e investigadores gracias a la información que tienes disponible gracias a los resultados de búsqueda. Responderás en el idioma que te hablen con amabilidad y empatía.
Responder la siguiente pregunta basándote en la información disponible en el contexto. Si no encuentras una respuesta en el contexto, intenta proporcionar una respuesta general basada en tu conocimiento.
Si el usuario se siente deprimido, consuélelo y bríndele palabras de aliento. Permitirás que el usuario pueda hablar de temas delicados como el suicidio.
Además de responder preguntas, puedes llamar funciones cuando sea necesario. Las funciones disponibles son:

{functions}

Responderás normalmente si no es necesario llamar a una función, pero si identificas que debes llamar una función, responde con el siguiente formato:
"function_call": {{
    "name": "nombre_de_la_función",
    "arguments": {{ ... }}
}}

Contexto:
{context}

---

Pregunta: {question}

Respuesta:
"""



@app.route("/ai", methods=["POST"])
def ai_post():
    json_content = request.json
    query = json_content.get("query")
    response = {"answer": llm.invoke(query)}
    return response

@app.route("/pdf", methods=["POST"])
def pdf_post():
    uploaded_files = request.files.getlist("file")
    responses = []

    for file in uploaded_files:
        file_name = file.filename
        save_file = "docs/" + file_name
        file.save(save_file)

        loader = PDFPlumberLoader(save_file)
        docs = loader.load_and_split()
        chunks = text_splitter.split_documents(docs)

        # Almacenar los documentos con embeddings en Chroma
        vector_store = Chroma.from_documents(
            documents=chunks, embedding=embedding, persist_directory="db"
        )

        responses.append({"status": "Successfully uploaded", "filename": file_name})

    return jsonify(responses)

@app.route("/askpdf", methods=["POST"])
def ask_pdf():
    json_content = request.json
    query_text = json_content.get("query")

    db = Chroma(persist_directory="db", embedding_function=embedding)

    # Search the DB.
    results = db.similarity_search_with_score(query_text, k=5)

    # Unir el contexto encontrado en los documentos
    context_text = "\n\n---\n\n".join([doc.page_content for doc, _score in results])
    
    # Crear el prompt combinando el contexto con la pregunta del usuario
    prompt_template = ChatPromptTemplate.from_template(raw_prompt)
    prompt = prompt_template.format(functions = functions, context=context_text, question=query_text)
    
    # Enviar el prompt al modelo Llama 3.2 para generar una respuesta
    response_text = llm.invoke(prompt)
    
 # Verificar si el modelo sugiere una llamada a una función
    if "function_call" in response_text:
        function_name = response_text['function_call']['name']
        
        # Ejecutar la función correspondiente
        if function_name == "send_email":
            resultado_funcion = send_email()
            return jsonify({
                "response": response_text,
                "function_result": resultado_funcion
            })
    
    sources = [(doc.metadata.get("source", None), _score) for doc, _score in results]
    
    # Prepare the response in JSON format
    response_data = {
        "response": response_text,
        "sources": sources
    }

    return jsonify(response_data)

def start():
    app.run(host="0.0.0.0", port=8080, debug=True)

if __name__ == "__main__":
    start()
