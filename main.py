from datetime import datetime, timedelta
import pandas as pd
from conexao_mongo import get_mongo_db

# 1. Carregar dados do banco Mongo
db = get_mongo_db()
turmas_cursor = db.classes_with_courses.find()
turmas = {str(t['_id']): t for t in turmas_cursor}

teachers = list(db.teachers_with_courses.find())
# Monta ALTERNANCIA dinamicamente de acordo com os professores e seus horários
ALTERNANCIA = {
    "manha": [t['nome_professor'] for t in teachers if t.get('horario_trabalho', {}).get('manha', False)],
    "tarde": [t['nome_professor'] for t in teachers if t.get('horario_trabalho', {}).get('tarde', False)],
    "noite": [t['nome_professor'] for t in teachers if t.get('horario_trabalho', {}).get('noite', False)]
}

# 2. Função utilitária para avançar para o próximo dia útil (segunda a sexta)
def prox_dia_util(data, add=1):
    data = datetime.strptime(data, "%d/%m/%Y")
    while add > 0:
        data += timedelta(days=1)
        if data.weekday() < 5:
            add -= 1
    return data.strftime("%d/%m/%Y")

# 3. Descobrir a maior data_fim "done" de cada turma (ponto de partida do cronograma)
def buscar_data_inicio(turma):
    datas_fim = [
        uc.get("data_fim")
        for uc in turma["unidades_curriculares"]
        if uc.get("data_fim")
    ]
    if datas_fim:
        return prox_dia_util(max(datas_fim, key=lambda x: datetime.strptime(x, "%d/%m/%Y")))
    else:
        return "17/02/2025"

# 4. Preparar o cronograma das UCs por turno
turmas_por_turno = {}
for turma_id, turma in turmas.items():
    turno = turma["turno"]
    if turno not in turmas_por_turno:
        turmas_por_turno[turno] = []
    turmas_por_turno[turno].append((turma_id, turma))

# 5. Rodar o ciclo de alocação para cada turno
relatorios = {}
for turno, turmas_do_turno in turmas_por_turno.items():
    ordem_professores = ALTERNANCIA.get(turno, [])
    if not ordem_professores:
        continue  # Nenhum professor disponível neste turno
    ciclo_prof = 0
    datas_atuais = {turma_id: buscar_data_inicio(turma) for turma_id, turma in turmas_do_turno}
    max_uc = max(
        len([uc for uc in turma["unidades_curriculares"] if uc.get("status") == "to do"])
        for _, turma in turmas_do_turno
    )
    for etapa in range(max_uc):
        for turma_id, turma in turmas_do_turno:
            uc_list = [
                uc for uc in sorted(turma["unidades_curriculares"], key=lambda x: x.get("ordem", 0))
                if uc.get("status") == "to do"
            ]
            if etapa >= len(uc_list):
                continue
            uc = uc_list[etapa]
            nome_uc = uc.get("nome")
            if not nome_uc:
                nome_uc = [v for k, v in uc.items() if k.startswith("uc_")]
                nome_uc = nome_uc[0] if nome_uc else "UC não informada"
            dias = uc.get("qtd_dias", 0)
            data_inicio = datas_atuais[turma_id]
            data_temp = data_inicio
            for _ in range(dias - 1):
                data_temp = prox_dia_util(data_temp)
            data_fim = data_temp
            # Alocar professor do ciclo
            if "Fundamentos de Eletroeletrônica Aplicada" in nome_uc:
                professor = None
            else:
                if ciclo_prof < len(ordem_professores):
                    professor = ordem_professores[ciclo_prof]
                else:
                    professor = None
            aviso = "PRECISA DE OUTRO PROFISSIONAL" if professor is None else ""
            if turma_id not in relatorios:
                relatorios[turma_id] = []
            relatorios[turma_id].append({
                "UC": nome_uc,
                "Data de Início": data_inicio,
                "Data de Fim": data_fim,
                "Professor": professor if professor else aviso
            })
            datas_atuais[turma_id] = prox_dia_util(data_fim)
        ciclo_prof = (ciclo_prof + 1) % len(ordem_professores)

# 6. Geração dos relatórios XLSX
for turma_id, rows in relatorios.items():
    turma_nome = turmas[turma_id]["codigo_turma"]
    df = pd.DataFrame(rows)
    nome_arquivo = f"relatorio_{turma_nome}.xlsx"
    df.to_excel(nome_arquivo, index=False)
    print(f"Relatório salvo: {nome_arquivo}")

# 7. Relatório geral dos professores (tudo agrupado)
linhas_geral = []
for turma_id, rows in relatorios.items():
    turma_nome = turmas[turma_id]["codigo_turma"]
    for row in rows:
        linhas_geral.append({
            "Turma": turma_nome,
            "UC": row["UC"],
            "Data de Início": row["Data de Início"],
            "Data de Fim": row["Data de Fim"],
            "Professor": row["Professor"]
        })
df_geral = pd.DataFrame(linhas_geral)
df_geral = df_geral.sort_values(["Professor", "Turma", "Data de Início"])
df_geral.to_excel("relatorio_geral_professores.xlsx", index=False)
print("Relatório geral de professores salvo: relatorio_geral_professores.xlsx")
