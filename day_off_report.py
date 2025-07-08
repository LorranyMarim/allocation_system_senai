import pandas as pd
from datetime import datetime

def professores_multiturno(teachers):
    """Retorna um dict {turno: [professores multiturno]}"""
    profs_multiturno = {}
    for t in teachers:
        turnos = [k.lower() for k,v in t.get("horario_trabalho", {}).items() if v is True or (isinstance(v,str) and v.lower()=='true')]
        if len(turnos) >= 2:
            for turno in turnos:
                profs_multiturno.setdefault(turno, []).append(t["nome_professor"])
    return profs_multiturno

def gerar_folgas_ciclicas_multiturno(turmas, teachers, filtro_turnos=None):
    """
    Gera rodízio de folgas apenas entre professores multiturno para cada turno.
    turmas: dict {id: turma_dict}
    teachers: list de professores (cada um dict)
    filtro_turnos: lista de turnos (str, minúsculo), ex: ['manha','tarde']
    """
    relatorio = []
    profs_multiturno = professores_multiturno(teachers)
    turnos_ativos = filtro_turnos if filtro_turnos else ['manha','tarde','noite']
    for turno in turnos_ativos:
        multiturnos = profs_multiturno.get(turno, [])
        if len(multiturnos) < 2:
            continue  # Rodízio só faz sentido para 2+ multiturno
        # UCs do turno
        ucs_turno = []
        for turma in turmas.values():
            if turma.get("turno", "").lower() == turno:
                for uc in sorted(turma.get("unidades_curriculares", []), key=lambda x: x.get("ordem", 0)):
                    nome_uc = uc.get("nome") or next((v for k, v in uc.items() if k.startswith("uc_")), "")
                    ucs_turno.append({
                        "Turma": turma["codigo_turma"],
                        "UC": nome_uc,
                        "Data de Início": uc.get("data_inicio"),
                        "Data de Fim": uc.get("data_fim"),
                    })
        for i, uc in enumerate(ucs_turno):
            idx_folga = i % len(multiturnos)
            alocados = [p for j, p in enumerate(multiturnos) if j != idx_folga]
            relatorio.append({
                "Turno": turno.capitalize(),
                "Ciclo": i+1,
                "Turma": uc["Turma"],
                "UC": uc["UC"],
                "Data Início": uc["Data de Início"],
                "Data Fim": uc["Data de Fim"],
                "Professores Alocados (multiturno)": ", ".join(alocados),
                "Professor de Folga (multiturno)": multiturnos[idx_folga]
            })
    return pd.DataFrame(relatorio)


# Exemplo de uso (comentado):
# from conexao_mongo import get_mongo_db
# db = get_mongo_db()
# turmas = {str(t['_id']): t for t in db.classes_with_courses.find()}
# teachers = list(db.teachers_with_courses.find())
# df_folgas = gerar_folgas_ciclicas_multiturno(turmas, teachers, filtro_turnos=['manha','tarde'])
# print(df_folgas.head())
