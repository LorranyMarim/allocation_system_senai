import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from conexao_mongo import get_mongo_db
from datetime import datetime as dt, timedelta

st.set_page_config(page_title="Relatórios Senai - TI", layout="wide")

st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            min-width: 455px !important;
            max-width: 455px !important;
            width: 455px !important;
            height: 911px !important;
            overflow-y: auto;
        }
        .turnos-label {
            font-size: 1rem !important;
            color: #223b6e !important;
            font-weight: 500 !important;
            margin-bottom: 0.5em;
        }
        .custom-container {
            background: #f9fafd;
            padding: 1.2rem;
            border-radius: 12px;
            border: 1px solid #e6e6ef;
        }
    </style>
""", unsafe_allow_html=True)

st.cache_data.clear()
st.cache_resource.clear()

@st.cache_data
def load_mongo_data():
    db = get_mongo_db()
    report_types = [
        {"description": "Cronograma de Turma"},
        {"description": "Alocação de Professores"},
    ]
    report_options = [rt["description"] for rt in report_types]
    classes = list(db.classes_with_courses.find())
    classes_options = [str(c.get("_id")) for c in classes]
    classes_df = pd.DataFrame(classes)
    teachers = list(db.teachers_with_courses.find())
    return report_options, classes, classes_options, classes_df, teachers

report_options, classes, classes_options, classes_df, teachers = load_mongo_data()

def get_detected_shifts(classes_selected, classes_df):
    detected_shifts = []
    for id_selected in classes_selected:
        row = classes_df[classes_df["_id"].astype(str) == str(id_selected)]
        if not row.empty:
            possible_shift_fields = ["shiftsType", "turnos", "turno"]
            shiftsType = None
            for field in possible_shift_fields:
                if field in row.columns:
                    shiftsType = row.iloc[0].get(field, None)
                    if shiftsType:
                        break
            if isinstance(shiftsType, list):
                detected_shifts.extend([t for t in shiftsType if t])
            elif isinstance(shiftsType, str):
                if "," in shiftsType:
                    detected_shifts.extend([s.strip() for s in shiftsType.split(",") if s.strip()])
                elif shiftsType.strip():
                    detected_shifts.append(shiftsType.strip())
    detected_shifts = sorted(set([s.strip().lower() for s in detected_shifts if s and s.lower() != "não informado"]))
    return detected_shifts

def get_teachers_by_shifts(detected_shifts, teachers):
    teacher_list = []
    normalized_shifts = [shift.strip().lower() for shift in detected_shifts]
    for t in teachers:
        horario = {k.strip().lower(): v for k, v in t.get("horario_trabalho", {}).items()}
        for shift in normalized_shifts:
            val = horario.get(shift, False)
            if val is True or (isinstance(val, str) and val.strip().lower() == "true"):
                teacher_list.append(t.get("nome_professor", str(t.get("_id"))))
    return sorted(set(teacher_list))

def get_turnos(teachers):
    all_turnos = set()
    for t in teachers:
        for turno in t.get("horario_trabalho", {}).keys():
            all_turnos.add(turno.lower())
    return sorted(list(all_turnos))

def prox_dia_util(data, add=1):
    data = dt.strptime(data, "%d/%m/%Y")
    while add > 0:
        data += timedelta(days=1)
        if data.weekday() < 5:
            add -= 1
    return data.strftime("%d/%m/%Y")

def buscar_data_inicio(turma):
    datas_fim = [
        uc.get("data_fim")
        for uc in turma["unidades_curriculares"]
        if uc.get("data_fim")
    ]
    if datas_fim:
        return prox_dia_util(max(datas_fim, key=lambda x: dt.strptime(x, "%d/%m/%Y")))
    else:
        return "17/02/2025"

def gerar_alocacao_cronograma(turmas, teachers, filtro_turmas=None, filtro_profs=None, status_uc=None, filtro_turnos=None):
    # Monta ALTERNANCIA dinamicamente de acordo com os professores e seus horários
    ALTERNANCIA = {
        "manha": [t['nome_professor'] for t in teachers if t.get('horario_trabalho', {}).get('manha', False)],
        "tarde": [t['nome_professor'] for t in teachers if t.get('horario_trabalho', {}).get('tarde', False)],
        "noite": [t['nome_professor'] for t in teachers if t.get('horario_trabalho', {}).get('noite', False)]
    }

    turmas_filtradas = {tid: t for tid, t in turmas.items() if (not filtro_turmas or tid in filtro_turmas)}
    if filtro_turnos:
        turmas_filtradas = {tid: t for tid, t in turmas_filtradas.items() if t["turno"].lower() in filtro_turnos}

    turmas_por_turno = {}
    for turma_id, turma in turmas_filtradas.items():
        turno = turma["turno"]
        if turno not in turmas_por_turno:
            turmas_por_turno[turno] = []
        turmas_por_turno[turno].append((turma_id, turma))

    relatorios = {}
    for turno, turmas_do_turno in turmas_por_turno.items():
        ordem_professores = ALTERNANCIA.get(turno, [])
        if not ordem_professores:
            continue  # Nenhum professor disponível neste turno
        ciclo_prof = 0
        datas_atuais = {turma_id: buscar_data_inicio(turma) for turma_id, turma in turmas_do_turno}
        max_uc = max(
            len([uc for uc in turma["unidades_curriculares"] if (uc.get("status") == "to do" if status_uc == "to do" else True)])
            for _, turma in turmas_do_turno
        )
        for etapa in range(max_uc):
            for turma_id, turma in turmas_do_turno:
                uc_list = [
                    uc for uc in sorted(turma["unidades_curriculares"], key=lambda x: x.get("ordem", 0))
                    if (uc.get("status") == status_uc if status_uc else uc.get("status") in ["to do", "done"])
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
                    "Turma": turma["codigo_turma"],
                    "Turno": turma["turno"],
                    "UC": nome_uc,
                    "Status": uc.get("status"),
                    "Data de Início": data_inicio,
                    "Data de Fim": data_fim,
                    "Professor": professor if professor else aviso,
                    "Qtd Dias": dias
                })
                datas_atuais[turma_id] = prox_dia_util(data_fim)
            ciclo_prof = (ciclo_prof + 1) % len(ordem_professores)
    # Junta tudo em um DataFrame geral
    linhas_geral = []
    for turma_id, rows in relatorios.items():
        for row in rows:
            linhas_geral.append(row)
    df_geral = pd.DataFrame(linhas_geral)
    # Filtro por professor se existir
    if filtro_profs:
        df_geral = df_geral[df_geral["Professor"].isin(filtro_profs)]
    return df_geral

def main():
    # Sidebar de filtros
    with st.sidebar:
        st.header("Filtros / Seleções")
        reporting_selected = st.selectbox(
            "Tipo de Relatório:",
            report_options,
            index=0
        )

        # Filtros Cronograma de Turma
        if reporting_selected == "Cronograma de Turma":
            classes_disabled = False
            classes_selected = st.multiselect(
                "Selecionar Turma:",
                classes_options,
                placeholder="Selecione uma ou mais turmas"
            )

            detected_shifts = []
            shifts_labels = "Nenhum"
            if len(classes_selected) >= 1:
                detected_shifts = get_detected_shifts(classes_selected, classes_df)
                if detected_shifts:
                    shifts_labels = ", ".join([s.capitalize() for s in detected_shifts])
            st.markdown(
                f'<div class="turnos-label">Turnos Detectados: <b>{shifts_labels}</b></div>',
                unsafe_allow_html=True
            )

            teacher_list = []
            teacher_name = []
            teachers_disabled = not (len(classes_selected) >= 1)
            if len(classes_selected) >= 1:
                teacher_list = get_teachers_by_shifts(detected_shifts, teachers) if detected_shifts else []
            teacher_name = st.multiselect(
                "Professores dos turnos selecionados:",
                teacher_list if teacher_list else ["Nenhum professor disponível para o(s) turno(s) selecionado(s)"],
                disabled=teachers_disabled
            )

            option_type_uc = {0: "Todas", 1: "Concluídas", 2: "Pendentes"}
            selection = st.segmented_control(
                label="Tipo de Unidade Curricular",
                options=option_type_uc.keys(),
                format_func=lambda option: option_type_uc[option],
                selection_mode="single",
                label_visibility="collapsed",
                disabled=not (len(classes_selected) >= 1)
            )
            generate_disabled = not (len(classes_selected) >= 1)
            generate_report = st.button("Gerar Relatório", disabled=generate_disabled)

        # Filtros Alocação de Professores
        elif reporting_selected == "Alocação de Professores":
            all_turnos = get_turnos(teachers)
            selected_turnos = st.multiselect(
                "Turnos:",
                all_turnos,
                placeholder="Selecione um ou mais turnos"
            )
            teacher_names_all = sorted(list(set([t["nome_professor"] for t in teachers])))
            teacher_name = st.multiselect(
                "Professor(es):",
                teacher_names_all,
                placeholder="Selecione um ou mais professores"
            )
            selection = None  # Não há status
            classes_selected = None  # Não há filtro por turma aqui
            generate_report = st.button("Gerar Relatório")

    st.title("Relatórios")

    # ------- DADOS MONGO ---------
    db = get_mongo_db()
    turmas_cursor = db.classes_with_courses.find()
    turmas = {str(t['_id']): t for t in turmas_cursor}

    # ---------- RELATÓRIO ----------
    if reporting_selected == "Cronograma de Turma" and 'generate_report' in locals() and generate_report:
        # Status UC
        status_map = {0: None, 1: "done", 2: "to do"}
        status_uc = status_map.get(selection)

        # Aplica filtros de turma, professor, status
        df_relatorio = gerar_alocacao_cronograma(
            turmas=turmas,
            teachers=teachers,
            filtro_turmas=classes_selected,
            filtro_profs=teacher_name,
            status_uc=status_uc
        )

        # Layout superior (Tabela + Gráfico Pizza)
        upper, lower = st.container(), st.container()
        with upper:
            col1, col2 = st.columns([3, 2], gap="large")
            with col1:
                st.subheader("Resultado da Alocação")
                if not df_relatorio.empty:
                    st.dataframe(
                        df_relatorio[["Turma", "UC", "Data de Início", "Data de Fim", "Professor"]],
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("Nenhuma UC encontrada para os filtros aplicados.")
            with col2:
                st.subheader("Proporção de UCs por Professor (Gráfico Pizza)")
                if not df_relatorio.empty:
                    df_pie = df_relatorio["Professor"].value_counts().reset_index()
                    df_pie.columns = ["Professor", "Qtd_UC"]
                    fig_pie = px.pie(df_pie, names="Professor", values="Qtd_UC", title="UCs por Professor")
                    fig_pie.update_traces(textinfo="value+label")
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    fig_pie = px.pie(values=[], names=[], title="UCs por Professor")
                    fig_pie.update_traces(textinfo='none')
                    st.plotly_chart(fig_pie, use_container_width=True)

        # Layout inferior (Gráfico de Barras)
        with lower:
            st.subheader("Tempo total de alocação por Professor (Gráfico Barras)")
            if not df_relatorio.empty:
                df_bar = df_relatorio.groupby("Professor")["Qtd Dias"].sum().reset_index()
                fig_bar = px.bar(df_bar, x="Professor", y="Qtd Dias", title="Total de Dias por Professor")
                fig_bar.update_layout(yaxis_title="Total de Dias")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                fig_bar = px.bar(x=[], y=[], title="Total de Dias por Professor")
                st.plotly_chart(fig_bar, use_container_width=True)

    elif reporting_selected == "Alocação de Professores" and 'generate_report' in locals() and generate_report:
        df_relatorio = gerar_alocacao_cronograma(
            turmas=turmas,
            teachers=teachers,
            filtro_profs=teacher_name if teacher_name else None,
            filtro_turnos=selected_turnos if selected_turnos else None
        )

        upper, lower = st.container(), st.container()
        with upper:
            col1, col2 = st.columns([3, 2], gap="large")
            with col1:
                st.subheader("UCs Alocadas (por Professor)")
                if not df_relatorio.empty:
                    st.dataframe(
                        df_relatorio[["Turma", "Turno", "UC", "Data de Início", "Data de Fim", "Professor"]],
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("Nenhum dado encontrado para o filtro.")
            with col2:
                st.subheader("Distribuição de UCs por Professor (Pizza)")
                if not df_relatorio.empty:
                    df_pie = df_relatorio["Professor"].value_counts().reset_index()
                    df_pie.columns = ["Professor", "Qtd_UC"]
                    fig_pie = px.pie(df_pie, names="Professor", values="Qtd_UC", title="UCs por Professor")
                    fig_pie.update_traces(textinfo="value+label")
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    fig_pie = px.pie(values=[], names=[], title="UCs por Professor")
                    fig_pie.update_traces(textinfo='none')
                    st.plotly_chart(fig_pie, use_container_width=True)

        with lower:
            st.subheader("Total de Dias de Alocação (por Professor) - Barras")
            if not df_relatorio.empty:
                df_bar = df_relatorio.groupby("Professor")["Qtd Dias"].sum().reset_index()
                fig_bar = px.bar(df_bar, x="Professor", y="Qtd Dias", title="Total de Dias por Professor")
                fig_bar.update_layout(yaxis_title="Total de Dias")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                fig_bar = px.bar(x=[], y=[], title="Total de Dias por Professor")
                st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Selecione os filtros e clique em Gerar Relatório para visualizar os dados.")

if __name__ == '__main__':
    main()
