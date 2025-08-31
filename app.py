import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import serial
from io import StringIO
import signal
import sys

# Serial config
SERIAL_PORT = "/dev/cu.usbserial-0001"
BAUD_RATE = 115200

# Open serial port globally (non-blocking)
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)

# Store all serial lines globally
all_lines = []

# Handle Ctrl+C clean exit
def signal_handler(sig, frame):
    print("\nStopping server...")
    ser.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Helper function to load + process Serial Data
def load_data():
    global all_lines
    # Read all available lines
    while ser.in_waiting > 0:
        try:
            line = ser.readline().decode("utf-8").strip()
        except Exception:
            continue
        if line:
            print(line)
            all_lines.append(line)

    # Find first CSV header
    header_line = None
    for l in all_lines:
        if l.startswith("id,"):  # only the real CSV header
            header_line = l
            break

    if not header_line:
        # no CSV header yet, return empty DataFrame
        return pd.DataFrame(columns=[
            "id","index","millis","gas_index","mes_index",
            "temperature","pressure","humidity","gas_resistance","status"
        ])

    # Only keep lines from the header onward
    start_idx = all_lines.index(header_line)
    csv_data = "\n".join(all_lines[start_idx:])
    df = pd.read_csv(StringIO(csv_data), on_bad_lines="skip")

    if "status" in df.columns:
        df = df[df["status"].astype(str) != "a0"]

    if "id" in df.columns and "index" in df.columns:
        df["sensor_key"] = df["id"].astype(str) + "_S" + df["index"].astype(str)

    return df

# Gas ticks function
def gas_ticks(ymin, ymax, n=6):
    ticks = np.linspace(ymin, ymax, n)
    ticktext = [f"{int(t):,} Ω\n({t:.0e})" for t in ticks]
    return ticks, ticktext

# Figure building
def make_figure(df, selected_sensor):
    sensors = df["sensor_key"].unique() if not df.empty else ["NoData"]
    d = df[df["sensor_key"] == selected_sensor].sort_values("millis") if not df.empty else pd.DataFrame()

    global_min = df["gas_resistance"].min() if not df.empty else 0
    global_max = df["gas_resistance"].max() if not df.empty else 1
    global_ticks, global_ticktext = gas_ticks(global_min, global_max)

    fig = make_subplots(
        rows=4, cols=2,
        specs=[[{"type":"scatter"}, {"type":"table"}],
               [{"type":"scatter"}, {"type":"table"}],
               [{"type":"scatter"}, None],
               [{"type":"scatter"}, None]],
        column_widths=[0.65, 0.35],
        row_heights=[0.50, 0.17, 0.17, 0.16],
        shared_xaxes=True,
        vertical_spacing=0.05
    )

    if not d.empty:
        fig.add_trace(go.Scatter(x=d["millis"], y=d["gas_resistance"], mode="lines+markers",
                                 name="Gas Resistance", hovertemplate="Gas: %{y:,.0f} Ω (%{y:.0e})<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=d["millis"], y=d["temperature"], mode="lines+markers",
                                 name="Temperature (°C)", hovertemplate="%{y:.2f} °C<extra></extra>"), row=2, col=1)
        fig.add_trace(go.Scatter(x=d["millis"], y=d["pressure"], mode="lines+markers",
                                 name="Pressure (Pa)", hovertemplate="%{y:.2f} Pa<extra></extra>"), row=3, col=1)
        fig.add_trace(go.Scatter(x=d["millis"], y=d["humidity"], mode="lines+markers",
                                 name="Humidity (%)", hovertemplate="%{y:.2f}%<extra></extra>"), row=4, col=1)

    fig.update_layout(template="plotly_dark", title=f"BME688 Dashboard - {selected_sensor}",
                      hovermode="x unified", height=1150, width=1500)
    return fig, sensors

# ------------------- DASH APP -------------------
app = Dash(__name__)

# Initial empty figure
df_init = pd.DataFrame()
fig_init, sensors_init = make_figure(df_init, "NoData")

app.layout = html.Div([
    html.H2("BME688 Live Dashboard", style={"color":"white", "textAlign":"center"}),
    dcc.Dropdown(id="sensor-dropdown", options=[{"label": s, "value": s} for s in sensors_init],
                 value=sensors_init[0], style={"width":"400px", "margin":"auto"}),
    dcc.Graph(id="live-graph", figure=fig_init),
    dcc.Interval(id="interval-refresh", interval=2000, n_intervals=0)
], style={"backgroundColor":"#111", "padding":"20px"})

@app.callback(Output("live-graph", "figure"),
              Input("interval-refresh", "n_intervals"),
              Input("sensor-dropdown", "value"))
def update_graph(n, selected_sensor):
    df = load_data()
    fig, _ = make_figure(df, selected_sensor)
    return fig

if __name__ == "__main__":
    app.run(debug=True, port=8050)
