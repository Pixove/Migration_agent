from langchain_community.chat_models import (
    ChatAnthropic,
    ChatGoogleGenerativeAI,
    ChatOllama,
    ChatOpenAI,
)
from langchain_community.embeddings import (
    HuggingFaceBgeEmbeddings,
    HuggingFaceEmbeddings,
    OllamaEmbeddings,
    OpenAIEmbeddings,
)
from langchain_community.llms import Anthropic, Ollama, OpenAI
from langchain_community.vectorstores import (
    Chroma,
    PGVector,
    Pinecone,
    Qdrant,
)

VECTOR_STORES = {
    "chroma": Chroma,
    "pgvector": PGVector,
    "pinecone": Pinecone,
    "qdrant": Qdrant,
}

LEGACY_LLMS = {
    "ollama": Ollama,
    "openai": OpenAI,
    "anthropic": Anthropic,
}


def build_embeddings(kind):
    if kind == "huggingface":
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    if kind == "huggingface-bge":
        return HuggingFaceBgeEmbeddings(model_name="BAAI/bge-small-zh-v1.5")
    if kind == "ollama":
        return OllamaEmbeddings(model="qwen2.5")
    return OpenAIEmbeddings(model="text-embedding-3-small")


def build_chat_model(provider):
    if provider == "ollama":
        return ChatOllama(model="qwen2.5")
    if provider == "openai":
        return ChatOpenAI(model="gpt-4o-mini")
    if provider == "anthropic":
        return ChatAnthropic(model="claude-3-5-sonnet")
    return ChatGoogleGenerativeAI(model="gemini-1.5-pro")


def build_vector_store(kind, embeddings):
    factory = VECTOR_STORES[kind]
    return factory(embedding_function=embeddings)
