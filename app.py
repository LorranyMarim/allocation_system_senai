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

def gerar_alocacao(
    turmas, teachers, 
    filtro_turmas=None, filtro_profs=None, status_uc=None, filtro_turnos=None
):
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
            continue
        ciclo_prof = 0
        datas_atuais = {turma_id: "17/02/2025" for turma_id, turma in turmas_do_turno}
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
    linhas_geral = []
    for turma_id, rows in relatorios.items():
        for row in rows:
            linhas_geral.append(row)
    df_geral = pd.DataFrame(linhas_geral)
    if filtro_profs:
        df_geral = df_geral[df_geral["Professor"].isin(filtro_profs)]
    return df_geral

def main():
    with st.sidebar:
        st.header("Filtros / Seleções")
        reporting_selected = st.selectbox(
            "Tipo de Relatório:",
            report_options,
            index=0
        )

        if reporting_selected == "Cronograma de Turma":
            classes_disabled = False
            classes_selected = st.multiselect(
                "Selecionar Turma:",
                classes_options,
                placeholder="Selecione uma ou mais turmas"
            )
            teacher_list = []
            teacher_name = []
            teachers_disabled = not (len(classes_selected) >= 1)
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
            selection = None
            classes_selected = None
            generate_report = st.button("Gerar Relatório")

    st.title("Relatórios")
    db = get_mongo_db()
    turmas_cursor = db.classes_with_courses.find()
    turmas = {str(t['_id']): t for t in turmas_cursor}

    # BLOCO DE "ALOCACAO DE PROFESSORES"
    if reporting_selected == "Alocação de Professores" and 'generate_report' in locals() and generate_report:
        df_relatorio = gerar_alocacao(
            turmas=turmas,
            teachers=teachers,
            filtro_profs=teacher_name if teacher_name else None,
            filtro_turnos=selected_turnos if selected_turnos else None
        )

        if not df_relatorio.empty:
            st.subheader("Indicadores Gerais")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de UCs", len(df_relatorio))
            col2.metric("UCs sem professor", df_relatorio['Professor'].str.contains("PRECISA DE OUTRO PROFISSIONAL").sum())
            col3.metric("Total de Professores", df_relatorio['Professor'].nunique())

            st.subheader("Distribuição de UCs por Professor")
            df_pie = df_relatorio["Professor"].value_counts().reset_index()
            df_pie.columns = ["Professor", "Qtd_UC"]
            fig_pie = px.pie(df_pie, names="Professor", values="Qtd_UC", title="UCs por Professor")
            fig_pie.update_traces(textinfo="value+label")
            st.plotly_chart(fig_pie, use_container_width=True)

            st.subheader("Carga de Dias por Professor")
            df_bar = df_relatorio.groupby("Professor")["Qtd Dias"].sum().reset_index()
            fig_bar = px.bar(df_bar, x="Professor", y="Qtd Dias", title="Total de Dias por Professor")
            fig_bar.update_layout(yaxis_title="Dias")
            st.plotly_chart(fig_bar, use_container_width=True)

            st.subheader("Professores no Limite de Alocação")
            limite_dias = 100  # Ajuste conforme realidade da carga horária máxima
            df_limite = df_bar[df_bar["Qtd Dias"] >= limite_dias]
            if not df_limite.empty:
                st.dataframe(df_limite, use_container_width=True)
            else:
                st.success(f"Nenhum professor acima do limite configurado ({limite_dias} dias)")

            st.subheader("Tabela Detalhada")
            st.dataframe(df_relatorio, use_container_width=True)

            csv = df_relatorio.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Baixar relatório em CSV",
                data=csv,
                file_name='relatorio_professores.csv',
                mime='text/csv',
            )
        else:
            st.info("Nenhuma alocação encontrada com os filtros selecionados.")

    # BLOCO DE "CRONOGRAMA DE TURMA"
    if reporting_selected == "Cronograma de Turma" and 'generate_report' in locals() and generate_report:
        status_map = {0: None, 1: "done", 2: "to do"}
        status_uc = status_map.get(selection)

        df_relatorio = gerar_alocacao(
            turmas=turmas,
            teachers=teachers,
            filtro_turmas=classes_selected,
            filtro_profs=teacher_name,
            status_uc=status_uc
        )

        if not df_relatorio.empty:
            st.subheader("Indicadores")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de UCs", len(df_relatorio))
            col2.metric("UCs sem professor", df_relatorio['Professor'].str.contains("PRECISA DE OUTRO PROFISSIONAL").sum())
            col3.metric("Total de Professores", df_relatorio['Professor'].nunique())

            st.subheader("Linha do Tempo (Cronograma Visual)")
            df_gantt = df_relatorio.copy()
            df_gantt['Data de Início'] = pd.to_datetime(df_gantt['Data de Início'], dayfirst=True)
            df_gantt['Data de Fim'] = pd.to_datetime(df_gantt['Data de Fim'], dayfirst=True)
            df_gantt['Turma - UC'] = df_gantt['Turma'] + " - " + df_gantt['UC'].astype(str)
            fig = px.timeline(
                df_gantt,
                x_start="Data de Início",
                x_end="Data de Fim",
                y="Turma - UC",
                color="Professor",
                text="Status",
                title="Cronograma de Turmas"
            )
            fig.update_yaxes(autorange="reversed")
            fig.update_layout(xaxis_title="Data", yaxis_title="Turma - UC", legend_title="Professor")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Tabela Detalhada do Cronograma")
            st.dataframe(df_relatorio, use_container_width=True)

            csv = df_relatorio.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Baixar tabela em CSV",
                data=csv,
                file_name='cronograma_turma.csv',
                mime='text/csv',
            )
        else:
            st.info("Nenhuma UC encontrada para os filtros aplicados.")

    if not (
        (reporting_selected == "Alocação de Professores" and 'generate_report' in locals() and generate_report) or
        (reporting_selected == "Cronograma de Turma" and 'generate_report' in locals() and generate_report)
    ):
        st.info("Selecione os filtros e clique em Gerar Relatório para visualizar os dados.")

if __name__ == '__main__':
    main()
