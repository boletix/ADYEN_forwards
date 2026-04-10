# Adyen Investment Monitor

Dashboard de indicadores adelantados para evaluar la tesis de inversión en Adyen (ADYEN.AS) antes del Q1 2026 Business Update (5 mayo 2026).

## Qué monitoriza

| Categoría | Indicador | Por qué importa |
|-----------|-----------|-----------------|
| **APAC Drag** | PDD Holdings (Temu) stock & GMV | Proxy directo del volumen de retailers APAC que arrastra a Adyen |
| **FX** | EUR/USD | Adyen reporta en EUR, mucho volumen es USD. Dólar débil = headwind reported |
| **E-commerce** | Shopify, Visa, Mastercard | Salud del e-commerce global y volúmenes cross-border |
| **Competidores** | PayPal, Worldline, Global Payments | Rendimiento relativo del sector pagos |
| **Valoración** | EV/FCF, FCF yield, upside a target | ¿Está barata o cara? |
| **Momentum** | Adyen 7d/30d returns | ¿El mercado anticipa algo? |

## Setup

```bash
pip install yfinance
python adyen_monitor.py
# Abre index.html en el navegador
```

## Deploy en GitHub Pages

1. Crea un repo en GitHub
2. Push del proyecto
3. Activa GitHub Pages (Settings → Pages → Source: GitHub Actions)
4. El workflow `daily-update.yml` corre cada día a las 18:00 UTC
5. También puedes ejecutarlo manualmente desde Actions → Adyen Monitor → Run workflow

## Estructura

```
adyen-monitor/
├── adyen_monitor.py          # Script principal
├── index.html                # Dashboard (auto-generado)
├── data/
│   ├── latest.json           # Último snapshot
│   └── snapshot_YYYY-MM-DD.json  # Archivo diario
├── .github/workflows/
│   └── daily-update.yml      # GitHub Actions para updates diarios
└── README.md
```

## Personalización

Edita las constantes en `adyen_monitor.py`:
- `ADYEN_FCF_TTM`, `ADYEN_EBITDA_TTM`: actualiza después de cada earnings
- `SIGNALS`: ajusta umbrales bull/bear según tu tesis
- `TICKERS`: añade/quita tickers a monitorizar

## Notas

- Los datos vienen de Yahoo Finance (gratis, sin API key)
- No es consejo de inversión
- Para app rankings de Temu/Shein necesitarías Sensor Tower o Data.ai (de pago)
