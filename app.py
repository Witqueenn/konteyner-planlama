import streamlit as st
import pandas as pd
import io
import itertools

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

    while not kalan_bobinler.empty:
        if hedef_konteyner_sayisi and len(planlar) >= hedef_konteyner_sayisi:
            break

        konteyner = []
        toplam_agirlik = 0
        alt_bobinler = []
        ust_bobinler = []

        kalan_bobinler = kalan_bobinler.sort_values(by="Ağırlık", ascending=False).reset_index(drop=True)
        altlar = kalan_bobinler[~kalan_bobinler["Üst Tabana Uygun"]].copy()
        ustler = kalan_bobinler[kalan_bobinler["Üst Tabana Uygun"]].copy()

        for alt_idx, alt_row in altlar.iterrows():
            if len(alt_bobinler) >= 11 or toplam_agirlik + alt_row["Ağırlık"] > ton_basina_yuk:
                continue

            matched = False
            for ust_idx, ust_row in ustler.iterrows():
                if len(ust_bobinler) >= 11:
                    break
                if alt_row["Uzunluk (cm)"] + ust_row["Uzunluk (cm)"] <= 2650:
                    if toplam_agirlik + alt_row["Ağırlık"] + ust_row["Ağırlık"] <= ton_basina_yuk:
                        alt_bobinler.append({**alt_row, "Taban": "Alt"})
                        ust_bobinler.append({**ust_row, "Taban": "Üst"})
                        toplam_agirlik += alt_row["Ağırlık"] + ust_row["Ağırlık"]
                        kalan_bobinler = kalan_bobinler.drop([alt_idx, ust_idx])
                        matched = True
                        break
            if not matched:
                if toplam_agirlik + alt_row["Ağırlık"] <= ton_basina_yuk:
                    alt_bobinler.append({**alt_row, "Taban": "Alt"})
                    toplam_agirlik += alt_row["Ağırlık"]
                    kalan_bobinler = kalan_bobinler.drop(alt_idx)

        ustler = kalan_bobinler[kalan_bobinler["Üst Tabana Uygun"]]
        for idx, ust_row in ustler.iterrows():
            if len(ust_bobinler) >= 11:
                break
            if toplam_agirlik + ust_row["Ağırlık"] <= ton_basina_yuk:
                ust_bobinler.append({**ust_row, "Taban": "Üst"})
                toplam_agirlik += ust_row["Ağırlık"]
                kalan_bobinler = kalan_bobinler.drop(idx)

        if toplam_agirlik < min_konteyner_tonaj:
            continue

        konteyner = alt_bobinler + ust_bobinler
        planlar.append((f"Konteyner {len(planlar) + 1} - Toplam Ağırlık: {round(toplam_agirlik)} kg", pd.DataFrame(konteyner)))

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
    ozet_grouped = ozet.groupby("Ürün Adı").agg({"Ağırlık": "sum"}).rename(columns={"Ağırlık": "Plana Alınan Toplam Order"})
    original_orders = df.set_index("Product Code")["Order"].to_dict()
    ozet_grouped["Toplam Order"] = ozet_grouped.index.map(original_orders)
    ozet_grouped["Kalan Order"] = ozet_grouped["Toplam Order"] - ozet_grouped["Plana Alınan Toplam Order"]

    st.dataframe(ozet_grouped.reset_index())
    ozet_grouped.to_excel(excel_output, sheet_name="Özet", index=True)
    excel_output.close()

    with open("planlar.xlsx", "rb") as f:
        st.download_button("📅 Excel olarak indir (Plan + Özet)", data=f, file_name="planlar.xlsx")
