import streamlit as st
import pandas as pd
import io
from itertools import combinations

st.set_page_config(layout="wide")
st.title("🚛 Konteyner Yükleme Planlama Aracı")

uploaded_file = st.file_uploader("📌 Dosya yükle (Excel formatında)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # Hesaplamalar
    df["Uzunluk (cm)"] = df["Product Code"].apply(lambda x: int(str(x).split("/")[2]))
    df["Bobin Ağırlığı (kg)"] = df["Uzunluk (cm)"] * 1.15
    df["Bobin Adedi"] = (df["Order"] / df["Bobin Ağırlığı (kg)"].astype(float)).round().astype(int)
    df["Üst Tabana Uygun"] = df["Uzunluk (cm)"] <= 1250
    st.dataframe(df)

    # Parametreler
    ton_basina_yuk = st.number_input("🧽 Maks konteyner tonajı (kg)", min_value=1000, max_value=30000, value=25000, step=500)
    min_konteyner_tonaj = st.number_input("🔻 Min konteyner tonajı (kg)", min_value=1000, max_value=ton_basina_yuk, value=20000, step=500)
    hedef_konteyner_sayisi = st.number_input("🎯 Hedef konteyner sayısı (0=tanımsız)", min_value=0, value=0, step=1)
    st.markdown(f"💡 Tonaj aralığı: **{min_konteyner_tonaj:,} - {ton_basina_yuk:,}** kg")

    # Bobin listesi
    rows = []
    for _, row in df.iterrows():
        for _ in range(row["Bobin Adedi"]):
            rows.append({
                "Ürün Adı": row["Product Code"],
                "Uzunluk (cm)": row["Uzunluk (cm)"],
                "Ağırlık": row["Bobin Ağırlığı (kg)"],
                "Üst Tabana Uygun": row["Üst Tabana Uygun"]
            })
    bobinler = pd.DataFrame(rows)
    bobinler = bobinler.reset_index(drop=True)

    # Sabitler
    MAX_ALT = 11
    MAX_UST = 11
    MAX_HIGH = 2650

    # Konteyner planlama fonksiyonu
    def konteyner_skora_gore_planla(bobin_df):
        altlar = bobin_df[~bobin_df["Üst Tabana Uygun"]].to_dict("records")
        ustler = bobin_df[bobin_df["Üst Tabana Uygun"]].to_dict("records")
        best_score = -1
        best_plan = []
        best_weight = 0
        # Tüm kombinasyon boyutları
        for alt_len in range(1, min(MAX_ALT, len(altlar)) + 1):
            for alt_combo in combinations(altlar, alt_len):
                alt_list = list(alt_combo)
                alt_weight = sum(b["Ağırlık"] for b in alt_list)
                # Üst bobin sayısı
                for ust_len in range(1, min(MAX_UST, len(ustler)) + 1):
                    for ust_combo in combinations(ustler, ust_len):
                        ust_list = list(ust_combo)
                        total_weight = alt_weight + sum(b["Ağırlık"] for b in ust_list)
                        # Tonaj sınırı
                        if total_weight > ton_basina_yuk or total_weight < min_konteyner_tonaj:
                            continue
                        # Yükseklik kontrolü
                        ok = True
                        for i in range(min(len(alt_list), len(ust_list))):
                            if alt_list[i]["Uzunluk (cm)"] + ust_list[i]["Uzunluk (cm)"] > MAX_HIGH:
                                ok = False
                                break
                        if not ok:
                            continue
                        # Skor: yükseklik uyum + tonaj yakınlık
                        height_score = sum(1 for i in range(min(len(alt_list), len(ust_list)))
                                           if alt_list[i]["Uzunluk (cm)"] + ust_list[i]["Uzunluk (cm)"] <= MAX_HIGH)
                        tonaj_score = 1 - abs(total_weight - ton_basina_yuk) / ton_basina_yuk
                        score = height_score + tonaj_score
                        if score > best_score:
                            best_score = score
                            best_plan = (alt_list, ust_list)
                            best_weight = total_weight
        # Etiketleme
        if best_plan:
            alt_list, ust_list = best_plan
            for b in alt_list: b["Taban"] = "Alt"
            for b in ust_list: b["Taban"] = "Üst"
            return alt_list + ust_list, best_weight
        return [], 0

    # Ana döngü
    planlar = []
    kalan = bobinler.copy()
    while not kalan.empty:
        if hedef_konteyner_sayisi and len(planlar) >= hedef_konteyner_sayisi:
            break
        plan, weight = konteyner_skora_gore_planla(kalan)
        if not plan:
            break
        # Kullanılan bobinleri kaldır
        used_idx = []
        for b in plan:
            idx = kalan[(kalan["Ürün Adı"] == b["Ürün Adı"]) & (kalan["Uzunluk (cm)"] == b["Uzunluk (cm)"])].index[0]
            used_idx.append(idx)
        kalan = kalan.drop(used_idx)
        planlar.append((f"Konteyner {len(planlar)+1} - {round(weight)} kg", pd.DataFrame(plan)))

    # Gösterim ve indirme
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
    grp = ozet[ozet["Plana Alındı"]].groupby("Ürün Adı").agg({"Ağırlık": "sum"}).rename(columns={"Ağırlık": "Plana Alınan"})
    grp["Toplam Order"] = [original_orders[k] for k in grp.index]
    grp["Kalan Order"] = grp["Toplam Order"] - grp["Plana Alındı"]
    st.dataframe(grp.reset_index())

    with open("planlar.xlsx", "rb") as f:
        st.download_button("📅 Excel indir (Plan+Özet)", data=f, file_name="planlar.xlsx")
