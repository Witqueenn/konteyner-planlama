import streamlit as st
import pandas as pd
import io

st.set_page_config(layout="wide")
st.title("🚛 Konteyner Yükleme Planlama Aracı")

uploaded_file = st.file_uploader("📎 Dosya yükle (Excel formatında)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # Uzunluğu Product Code’dan çek
    df["Uzunluk (cm)"] = df["Product Code"].apply(lambda x: int(str(x).split("/")[2]))
    df["Bobin Ağırlığı (kg)"] = df["Uzunluk (cm)"] * 1.15
    df["Bobin Adedi"] = (df["Order"] / df["Bobin Ağırlığı (kg)"]).round().astype(int)
    df["Üst Tabana Uygun"] = df["Uzunluk (cm)"] <= 1250

    st.dataframe(df)

    # Planlamaya başlamadan önce tonaj sorulsun
    ton_basina_yuk = st.number_input("🧮 Her bir konteyner planı için maksimum tonaj girin (kg)", min_value=1000, max_value=30000, value=25000, step=500)
    st.markdown(f"💡 Her konteyner için maksimum yükleme sınırı: **{ton_basina_yuk:,} kg**")

    # Bobinleri satır satır çoğaltalım
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
    bobinler = bobinler.sort_values(by="Ağırlık", ascending=False).reset_index(drop=True)

    planlar = []
    kalan_bobinler = bobinler.copy()

    while not kalan_bobinler.empty:
        konteyner = []
        toplam_agirlik = 0
        alt_sayac = 0
        ust_sayac = 0

        for idx in list(kalan_bobinler.index):
            bobin = kalan_bobinler.loc[idx]
            if toplam_agirlik + bobin["Ağırlık"] > ton_basina_yuk:
                continue

            if not bobin["Üst Tabana Uygun"] and alt_sayac < 11:
                konteyner.append({**bobin, "Taban": "Alt"})
                alt_sayac += 1
                toplam_agirlik += bobin["Ağırlık"]
                kalan_bobinler = kalan_bobinler.drop(idx)
            elif bobin["Üst Tabana Uygun"]:
                if alt_sayac < 11:
                    konteyner.append({**bobin, "Taban": "Alt"})
                    alt_sayac += 1
                    toplam_agirlik += bobin["Ağırlık"]
                    kalan_bobinler = kalan_bobinler.drop(idx)
                elif ust_sayac < 11:
                    konteyner.append({**bobin, "Taban": "Üst"})
                    ust_sayac += 1
                    toplam_agirlik += bobin["Ağırlık"]
                    kalan_bobinler = kalan_bobinler.drop(idx)

        planlar.append((f"Konteyner {len(planlar) + 1} - Toplam Ağırlık: {round(toplam_agirlik)} kg", pd.DataFrame(konteyner)))

    st.subheader("📦 Konteyner Planları")
    for plan_adi, tablo in planlar:
        st.markdown(f"### {plan_adi}")
        st.dataframe(tablo.reset_index(drop=True))

    # Özet oluştur
    st.subheader("📊 Planlama Özeti")
    toplam_df = pd.concat([plan for _, plan in planlar])
    toplam_df = toplam_df.merge(df[["Product Code", "Order"]], left_on="Ürün Adı", right_on="Product Code", how="left")

    summary = toplam_df.groupby("Ürün Adı").agg({
        "Ağırlık": "sum",
        "Order": "first"
    }).reset_index()
    summary.rename(columns={"Ağırlık": "Planlanan Yük (kg)", "Order": "Toplam Sipariş (kg)"}, inplace=True)
    summary["Kalan Sipariş (kg)"] = summary["Toplam Sipariş (kg)"] - summary["Planlanan Yük (kg)"]

    st.dataframe(summary)

    # Excel çıktısı indir
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        summary.to_excel(writer, index=False, sheet_name="Özet")

    st.download_button(
        label="📥 Özeti Excel olarak indir",
        data=output.getvalue(),
        file_name="konteyner_ozet.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )