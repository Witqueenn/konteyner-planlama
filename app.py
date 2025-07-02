import streamlit as st
import pandas as pd
import math
from itertools import combinations

st.set_page_config(layout="wide")
st.title("🚛 Konteyner Yükleme Planlama Aracı")

uploaded_file = st.file_uploader("📌 Dosya yükle (Excel formatında)", type=["xlsx"])
if not uploaded_file:
    st.info("Lütfen bir Excel dosyası yükleyin.")
else:
    df = pd.read_excel(uploaded_file)
    df["Uzunluk (cm)"] = df["Product Code"].apply(lambda x: int(str(x).split("/")[2]))
    df["Bobin Ağırlığı (kg)"] = df["Uzunluk (cm)"] * 1.15
    df["Bobin Adedi"] = (df["Order"] / df["Bobin Ağırlığı (kg)"].astype(float)).round().astype(int)
    df["Üst Tabana Uygun"] = df["Uzunluk (cm)"] <= 1250
    st.dataframe(df)

    ton_basina_yuk = st.number_input(
        "🧽 Maks konteyner tonajı (kg)", min_value=1000, max_value=30000, value=25000, step=500)
    min_konteyner_tonaj = st.number_input(
        "🔻 Min konteyner tonajı (kg)", min_value=1000, max_value=ton_basina_yuk, value=20000, step=500)
    hedef_konteyner_sayisi = st.number_input(
        "🎯 Hedef konteyner sayısı (0=tanımsız)", min_value=0, value=0, step=1)
    st.markdown(f"💡 Tonaj aralığı: **{min_konteyner_tonaj:,} - {ton_basina_yuk:,}** kg")

    if st.button("🎬 Konteyner Planı Oluştur"):
        rows = []
        for _, row in df.iterrows():
            for _ in range(row["Bobin Adedi"]):
                rows.append({
                    "Ürün Adı": row["Product Code"],
                    "Uzunluk (cm)": row["Uzunluk (cm)"],
                    "Ağırlık": row["Bobin Ağırlığı (kg)"],
                    "Üst Tabana Uygun": row["Üst Tabana Uygun"]
                })
        bobinler = pd.DataFrame(rows).reset_index(drop=True)

        MAX_ALT, MAX_UST, MAX_HIGH = 11, 11, 2650
        altlar_df = bobinler[~bobinler["Üst Tabana Uygun"]]
        ustler_df = bobinler[bobinler["Üst Tabana Uygun"]]
        n_alt, n_ust = len(altlar_df), len(ustler_df)
        total_alt = sum(math.comb(n_alt, a) for a in range(1, min(MAX_ALT, n_alt) + 1))
        total_ust = sum(math.comb(n_ust, u) for u in range(0, min(MAX_UST, n_ust) + 1))
        total_iter = total_alt * total_ust
        progress = st.progress(0)
        iter_count = [0]

        def konteyner_skora_gore_planla(kalan_df):
            alt_records = kalan_df[~kalan_df["Üst Tabana Uygun"]].to_dict("records")
            ust_records = kalan_df[kalan_df["Üst Tabana Uygun"]].to_dict("records")
            best_score, best_plan, best_weight = -1, ([], []), 0

            for alt_len in range(1, min(MAX_ALT, len(alt_records)) + 1):
                for alt_combo in combinations(alt_records, alt_len):
                    alt_list = list(alt_combo)
                    alt_w = sum(b["Ağırlık"] for b in alt_list)

                    for ust_len in range(0, min(MAX_UST, len(ust_records)) + 1):
                        for ust_combo in combinations(ust_records, ust_len):
                            ust_list = list(ust_combo)
                            w = alt_w + sum(b["Ağırlık"] for b in ust_list)
                            if w > ton_basina_yuk or w < min_konteyner_tonaj:
                                continue
                            height_ok = True
                            for i in range(min(len(alt_list), len(ust_list))):
                                if alt_list[i]["Uzunluk (cm)"] + ust_list[i]["Uzunluk (cm)"] > MAX_HIGH:
                                    height_ok = False
                                    break
                            if not height_ok:
                                continue

                            height_score = sum(
                                1 for i in range(min(len(alt_list), len(ust_list)))
                                if alt_list[i]["Uzunluk (cm)"] + ust_list[i]["Uzunluk (cm)"] <= MAX_HIGH
                            )
                            tonaj_score = 1 - abs(w - ton_basina_yuk) / ton_basina_yuk
                            score = height_score + tonaj_score

                            iter_count[0] += 1
                            progress.progress(min(iter_count[0] / total_iter, 1.0))

                            if score > best_score:
                                best_score, best_plan, best_weight = score, (alt_list, ust_list), w

            alt_list, ust_list = best_plan
            for b in alt_list:
                b["Taban"] = "Alt"
            for b in ust_list:
                b["Taban"] = "Üst"
            return alt_list + ust_list, best_weight

        planlar = []
        kalan = bobinler.copy()
        while not kalan.empty:
            if hedef_konteyner_sayisi and len(planlar) >= hedef_konteyner_sayisi:
                break
            plan, weight = konteyner_skora_gore_planla(kalan)
            if not plan:
                break
            used_idx = []
            for b in plan:
                idx = kalan[
                    (kalan["Ürün Adı"] == b["Ürün Adı"]) &
                    (kalan["Uzunluk (cm)"] == b["Uzunluk (cm)"])
                ].index[0]
                used_idx.append(idx)
            kalan = kalan.drop(used_idx)
            planlar.append((f"Konteyner {len(planlar)+1} - {round(weight)} kg", pd.DataFrame(plan)))

        st.subheader("📦 Konteyner Planları")
        writer = pd.ExcelWriter("planlar.xlsx", engine="xlsxwriter")
        for i, (title, df_plan) in enumerate(planlar, 1):
            st.markdown(f"### {title}")
            st.dataframe(df_plan)
            df_plan.to_excel(writer, sheet_name=f"Plan {i}", index=False)
        writer.close()

        st.subheader("📊 Özet Rapor")
        ozet = bobinler.copy()
        ozet["Plana Alındı"] = ~kalan.index.isin(bobinler.index)
        original_orders = df.set_index("Product Code")["Order"].to_dict()
        grp = (
            ozet[ozet["Plana Alındı"]]
            .groupby("Ürün Adı")
            .agg({"Ağırlık": "sum"})
            .rename(columns={"Ağırlık": "Plana Alındı"})
        )
        grp["Toplam Order"] = [original_orders[k] for k in grp.index]
        grp["Kalan Order"] = grp["Toplam Order"] - grp["Plana Alındı"]
        st.dataframe(grp.reset_index())

        with open("planlar.xlsx", "rb") as f:
            st.download_button("📅 Excel indir (Plan+Özet)", data=f, file_name="planlar.xlsx")

