import streamlit as st
import pandas as pd
import io
from itertools import combinations

st.set_page_config(layout="wide")
st.title("🚛 Konteyner Yükleme Planlama Aracı")

uploaded_file = st.file_uploader("📌 Dosya yükle (Excel formatında)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    df["Uzunluk (cm)"] = df["Product Code"].apply(lambda x: int(str(x).split("/")[2]))
    df["Bobin Ağırlığı (kg)"] = df["Uzunluk (cm)"] * 1.15
    df["Bobin Adedi"] = (df["Order"] / df["Bobin Ağırlığı (kg)"].astype(float)).round().astype(int)
    df["Üst Tabana Uygun"] = df["Uzunluk (cm)"] <= 1250

    st.dataframe(df)

    ton_basina_yuk = st.number_input("🧽 Her bir konteyner planı için maksimum tonaj girin (kg)", min_value=1000, max_value=30000, value=25000, step=500)
    min_konteyner_tonaj = st.number_input("🔻 Minimum kabul edilebilir konteyner tonajı (kg)", min_value=1000, max_value=ton_basina_yuk, value=20000, step=500)
    hedef_konteyner_sayisi = st.number_input("🎯 Hedef konteyner sayısı (isteğe bağlı)", min_value=0, value=0, step=1)

    st.markdown(f"💡 Her konteyner için yükleme sınırı: **{ton_basina_yuk:,} kg**, minimum: **{min_konteyner_tonaj:,} kg**")

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
    planlar = []
    kalan_bobinler = bobinler.copy()

    def hesapla_skor(alt, ust, max_uzunluk=2650, hedef_tonaj=25000):
        toplam_agirlik = sum(b["Ağırlık"] for b in alt + ust)
        yukseklik_uyum_skoru = sum(
            1 for i in range(min(len(alt), len(ust)))
            if alt[i]["Uzunluk (cm)"] + ust[i]["Uzunluk (cm)"] <= max_uzunluk
        )
        tonaj_yakinlik_skoru = max(0, 1 - abs(toplam_agirlik - hedef_tonaj) / hedef_tonaj)
        return yukseklik_uyum_skoru + tonaj_yakinlik_skoru, toplam_agirlik

    while not kalan_bobinler.empty:
        if hedef_konteyner_sayisi and len(planlar) >= hedef_konteyner_sayisi:
            break

        alt_bobinler_all = kalan_bobinler[kalan_bobinler["Üst Tabana Uygun"] == False].to_dict("records")
        ust_bobinler_all = kalan_bobinler[kalan_bobinler["Üst Tabana Uygun"] == True].to_dict("records")

        en_iyi_skor = -1
        en_iyi_alt = []
        en_iyi_ust = []

        for alt_combo in combinations(alt_bobinler_all, min(11, len(alt_bobinler_all))):
            for ust_combo in combinations(ust_bobinler_all, min(11, len(ust_bobinler_all))):
                skor, agirlik = hesapla_skor(list(alt_combo), list(ust_combo), 2650, ton_basina_yuk)
                if agirlik <= ton_basina_yuk and agirlik >= min_konteyner_tonaj and skor > en_iyi_skor:
                    en_iyi_skor = skor
                    en_iyi_alt = list(alt_combo)
                    en_iyi_ust = list(ust_combo)

        if not en_iyi_alt and not en_iyi_ust:
            break

        for b in en_iyi_alt + en_iyi_ust:
            kalan_bobinler = kalan_bobinler.drop(kalan_bobinler[(kalan_bobinler["Ürün Adı"] == b["Ürün Adı"]) & (kalan_bobinler["Uzunluk (cm)"] == b["Uzunluk (cm)"])].index[0])

        for b in en_iyi_alt:
            b["Taban"] = "Alt"
        for b in en_iyi_ust:
            b["Taban"] = "Üst"

        konteyner = en_iyi_alt + en_iyi_ust
        planlar.append((f"Konteyner {len(planlar) + 1} - Toplam Ağırlık: {round(sum(b['Ağırlık'] for b in konteyner))} kg", pd.DataFrame(konteyner)))

    st.subheader("📦 Konteyner Planları")
    excel_output = pd.ExcelWriter("planlar.xlsx", engine="xlsxwriter")
    for i, (plan_adi, tablo) in enumerate(planlar):
        st.markdown(f"### {plan_adi}")
        st.dataframe(tablo.reset_index(drop=True))
        tablo.to_excel(excel_output, sheet_name=f"Plan {i+1}", index=False)

    st.subheader("📊 Özet Rapor")
    toplam_konteyner = len(planlar)
    st.write(f"Toplam konteyner sayısı: **{toplam_konteyner}**")

    ozet = bobinler.copy()
    ozet["Plana Alındı"] = True
    original_orders = df.set_index("Product Code")["Order"].to_dict()
    ozet_grouped = ozet.groupby("Ürün Adı").agg({
        "Ağırlık": "sum"
    }).rename(columns={"Ağırlık": "Plana Alınan Toplam Order"})
    ozet_grouped["Toplam Order"] = ozet_grouped.index.map(original_orders)
    ozet_grouped["Kalan Order"] = ozet_grouped["Toplam Order"] - ozet_grouped["Plana Alınan Toplam Order"]

    st.dataframe(ozet_grouped.reset_index())
    ozet_grouped.to_excel(excel_output, sheet_name="Özet", index=True)
    excel_output.close()

    with open("planlar.xlsx", "rb") as f:
        st.download_button("📅 Excel olarak indir (Plan + Özet)", data=f, file_name="planlar.xlsx")
