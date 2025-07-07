from pymongo import MongoClient

def get_mongo_db():
    # Conecta ao MongoDB local (localhost, porta padrão 27017)
    client = MongoClient("mongodb://localhost:27017/")
    
    # Seleciona o banco de dados
    db = client["alocacao_senai"]
    return db

# Exemplo de uso:
if __name__ == "__main__":
    db = get_mongo_db()
    print("Coleções disponíveis na base 'alocacao_senai':")
    print(db.list_collection_names())
