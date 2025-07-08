from datetime import datetime as dt
import pandas as pd
from conexao_mongo import get_mongo_db

# 1. Carregar dados do banco Mongo
db = get_mongo_db()
turmas_cursor = db.classes_with_courses.find()
turmas = {str(t['_id']): t for t in turmas_cursor}
teachers = list(db.teachers_with_courses.find())

# 2. Montar alternância fixa de professores por turno, em ordem crescente de _id
def ordenar_professores(teachers, turno):
    profs_turno = [t for t in teachers 
                   if t.get('horario_trabalho', {}).get(turno, False) 
                   and str(t.get('_id', '')).startswith('Prof_')]
    # Ordena pelo número incremental do _id (ex: Prof_1, Prof_2, ...)
    profs_turno.sort(key=lambda t: int(str(t['_id']).replace('Prof_', '')))
    return [t['nome_professor'] for t in profs_turno]

FILA = {
    turno: ordenar_professores(teachers, turno)
    for turno in ['manha', 'tarde', 'noite']
}

# 3. Função para ordenar UCs "to do" com datas já informadas
def ordenar_ucs_to_do(turmas):
    ucs = []
    for turma_id, turma in turmas.items():
        for uc in turma.get("unidades_curriculares", []):
            if uc.get("status") == "to do":
                ucs.append({
                    "turma_id": turma_id,
                    "Turma": turma.get("codigo_turma"),
                    "Turno": turma.get("turno").lower(),
                    "UC": uc.get("nome"),
                    "data_inicio": uc.get("data_inicio"),
                    "data_fim": uc.get("data_fim"),
                })
    return sorted(ucs, key=lambda x: dt.strptime(x["data_inicio"], "%d/%m/%Y"))

# 4. Função para verificar sobreposição de datas
def overlap(start1, end1, start2, end2):
    return not (end1 < start2 or start1 > end2)

# 5. Geração da alocação híbrida
def gerar_alocacao_hibrida(turmas, teachers):
    ucs = ordenar_ucs_to_do(turmas)
    ocupacoes = {t["nome_professor"]: [] for t in teachers}
    ponteiro = {turno: 0 for turno in FILA}  # Fixa a ordem dos professores

    alocacoes = []
    for entry in ucs:
        turno = entry["Turno"]
        profs = FILA.get(turno, [])
        escolhido = None
        start = dt.strptime(entry["data_inicio"], "%d/%m/%Y")
        end = dt.strptime(entry["data_fim"], "%d/%m/%Y")
        if not profs:
            escolhido = "SEM PROFESSOR DISPONÍVEL"
        else:
            for i in range(len(profs)):
                idx = (ponteiro[turno] + i) % len(profs)
                prof = profs[idx]
                conflitos = any(overlap(start, end, os_start, os_end)
                                for os_start, os_end in ocupacoes[prof])
                if not conflitos:
                    escolhido = prof
                    ocupacoes[prof].append((start, end))
                    ponteiro[turno] = (idx + 1) % len(profs)  # avança ponteiro da alternância
                    break
            if not escolhido:
                escolhido = "SEM PROFESSOR DISPONÍVEL"
        alocacoes.append({
            "Turma": entry["Turma"],
            "UC": entry["UC"],
            "Data de Início": entry["data_inicio"],
            "Data de Fim": entry["data_fim"],
            "Professor": escolhido
        })
    return pd.DataFrame(alocacoes)

# 6. Gera relatório
df_alocacao = gerar_alocacao_hibrida(turmas, teachers)
df_alocacao.to_excel("relatorio_alocacao_hibrido.xlsx", index=False)
print("Relatório salvo: relatorio_alocacao_hibrido.xlsx")
def gerar_alocacao_hibrida_streamlit(turmas, teachers, filtro_turmas=None, filtro_profs=None, status_uc=None, filtro_turnos=None):
    # 1. Filtra turmas conforme necessário
    turmas_filtradas = {tid: t for tid, t in turmas.items() if (not filtro_turmas or tid in filtro_turmas)}
    if filtro_turnos:
        turmas_filtradas = {tid: t for tid, t in turmas_filtradas.items() if t["turno"].lower() in filtro_turnos}

    # 2. Monta alternância fixa de professores por turno, usando _id Prof_*
    def ordenar_professores(teachers, turno):
        profs_turno = [t for t in teachers 
                       if t.get('horario_trabalho', {}).get(turno, False) 
                       and str(t.get('_id', '')).startswith('Prof_')]
        profs_turno.sort(key=lambda t: int(str(t['_id']).replace('Prof_', '')))
        return [t['nome_professor'] for t in profs_turno]
    FILA = {
        turno: ordenar_professores(teachers, turno)
        for turno in ['manha', 'tarde', 'noite']
    }

    # 3. Ordena UCs "to do" (ou todas) por data de início informada
    ucs = []
    for turma_id, turma in turmas_filtradas.items():
        for uc in turma.get("unidades_curriculares", []):
            if ((status_uc is None and uc.get("status") in ["to do", "done"]) or
                (status_uc is not None and uc.get("status") == status_uc)):
                ucs.append({
                    "turma_id": turma_id,
                    "Turma": turma.get("codigo_turma"),
                    "Turno": turma.get("turno").lower(),
                    "UC": uc.get("nome"),
                    "Status": uc.get("status"),
                    "Qtd Dias": uc.get("qtd_dias"),
                    "data_inicio": uc.get("data_inicio"),
                    "data_fim": uc.get("data_fim"),
                })
    ucs = sorted(ucs, key=lambda x: dt.strptime(x["data_inicio"], "%d/%m/%Y"))

    # 4. Alocação considerando alternância fixa e sem sobreposição
    def overlap(start1, end1, start2, end2):
        return not (end1 < start2 or start1 > end2)
    ocupacoes = {t["nome_professor"]: [] for t in teachers}
    ponteiro = {turno: 0 for turno in FILA}

    alocacoes = []
    for entry in ucs:
        turno = entry["Turno"]
        profs = FILA.get(turno, [])
        escolhido = None
        start = dt.strptime(entry["data_inicio"], "%d/%m/%Y")
        end = dt.strptime(entry["data_fim"], "%d/%m/%Y")
        if not profs:
            escolhido = "SEM PROFESSOR DISPONÍVEL"
        else:
            for i in range(len(profs)):
                idx = (ponteiro[turno] + i) % len(profs)
                prof = profs[idx]
                conflitos = any(overlap(start, end, os_start, os_end)
                                for os_start, os_end in ocupacoes[prof])
                if not conflitos:
                    escolhido = prof
                    ocupacoes[prof].append((start, end))
                    ponteiro[turno] = (idx + 1) % len(profs)
                    break
            if not escolhido:
                escolhido = "SEM PROFESSOR DISPONÍVEL"
        alocacoes.append({
            "Turma": entry["Turma"],
            "Turno": turno,
            "UC": entry["UC"],
            "Status": entry["Status"],
            "Data de Início": entry["data_inicio"],
            "Data de Fim": entry["data_fim"],
            "Professor": escolhido,
            "Qtd Dias": entry["Qtd Dias"]
        })

    df_geral = pd.DataFrame(alocacoes)
    # Filtro final por professor, se houver
    if filtro_profs:
        df_geral = df_geral[df_geral["Professor"].isin(filtro_profs)]
    return df_geral
