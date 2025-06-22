import base64
import io
import pandas as pd
from dash import Dash, dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc

# === Your existing parsing logic and app setup ===

# === Header Mapping ===
COL_MAP = {
    'MD': ['md', 'measured depth', 'survey depth', 'sd', 'survey'],
    'INC': ['inc', 'inclination'],
    'AZ': ['az', 'azi', 'azimuth', 'azm']
}

def standardize_headers(headers):
    lower_headers = [str(h).lower().strip() for h in headers]
    result = []
    for h in lower_headers:
        for std_key, aliases in COL_MAP.items():
            if h in aliases:
                result.append(std_key)
                break
        else:
            result.append(None)
    return result

def parse_survey_file(contents, filename, survey_type):
    def try_parse(df, header_row_idx, header_cols, data_start_row_idx, data_cols):
        headers = df.iloc[header_row_idx, header_cols].tolist()
        std_headers = standardize_headers(headers)
        if None in std_headers:
            raise ValueError(f"Unknown header detected in {survey_type} file: {headers}")
        
        data_df = df.iloc[data_start_row_idx:, data_cols].dropna(how='all')  # Remove blank rows
        data_df.columns = std_headers
        data_df[['MD', 'INC', 'AZ']] = data_df[['MD', 'INC', 'AZ']].apply(pd.to_numeric, errors='coerce')
        data_df = data_df.dropna(subset=['MD', 'INC', 'AZ']).reset_index(drop=True)

        for col in ['MD', 'INC', 'AZ']:
            data_df[col] = data_df[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
        return data_df

    # === Decode and read file ===
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    if filename.endswith('.csv'):
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), header=None)
    elif filename.endswith('.xls') or filename.endswith('.xlsx'):
        df = pd.read_excel(io.BytesIO(decoded), header=None)
    else:
        raise ValueError("Unsupported file type")

    # === Remove completely blank rows early ===
    df = df.dropna(how='all').reset_index(drop=True)

    # === Try primary known format ===
    try:
        if survey_type == "MWD":
            return try_parse(df, 16, [1, 2, 3], 18, [1, 2, 3])
        else:
            return try_parse(df, 54, [0, 1, 2], 56, [0, 1, 2])
    except Exception:
        pass  # Fall through to fallback methods

    # === Try keyword-based detection ===
    try:
        for i in range(min(100, len(df))):
            row = df.iloc[i].astype(str).str.lower()
            matches = [any(cell in aliases for cell in row) for aliases in COL_MAP.values()]
            if all(matches):
                header_row_idx = i
                data_start_idx = i + 1
                cols = [j for j, cell in enumerate(row) if any(cell in aliases for aliases in COL_MAP.values())]
                headers = df.iloc[header_row_idx, cols].tolist()
                std_headers = standardize_headers(headers)
                if None in std_headers or len(std_headers) != 3:
                    raise ValueError("Keyword-based header detection failed.")

                data_df = df.iloc[data_start_idx:, cols].dropna(how='all')
                data_df.columns = std_headers
                data_df[['MD', 'INC', 'AZ']] = data_df[['MD', 'INC', 'AZ']].apply(pd.to_numeric, errors='coerce')
                data_df = data_df.dropna(subset=['MD', 'INC', 'AZ']).reset_index(drop=True)

                for col in ['MD', 'INC', 'AZ']:
                    data_df[col] = data_df[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
                return data_df
    except Exception:
        pass  # Fall through to Well Seeker Pro fallback

    # === Try Well Seeker Pro fallback ===
    try:
        headers = df.iloc[69, [0, 1, 2]].tolist()  # A70:C70
        std_headers = standardize_headers(headers)
        if None in std_headers:
            raise ValueError(f"Unknown header detected in WSP fallback: {headers}")

        # Determine start row (skip non-numeric first row if needed)
        first_data_row = 71  # row 72
        sample = df.iloc[first_data_row, [0, 1, 2]]
        if not all(pd.to_numeric(sample, errors='coerce').notna()):
            first_data_row += 1

        data_df = df.iloc[first_data_row:, [0, 1, 2]].dropna(how='all')
        data_df.columns = std_headers
        data_df[['MD', 'INC', 'AZ']] = data_df[['MD', 'INC', 'AZ']].apply(pd.to_numeric, errors='coerce')
        data_df = data_df.dropna(subset=['MD', 'INC', 'AZ']).reset_index(drop=True)

        for col in ['MD', 'INC', 'AZ']:
            data_df[col] = data_df[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
        return data_df
    except Exception as e:
        raise ValueError(f"Failed all parsing methods: {str(e)}")

# === App Setup ===
app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
app.title = "Side by Side"
app._favicon = "favicon.ico"  # Place favicon.ico in /assets folder

# === Custom Styles ===
CUSTOM_STYLES = {
    'upload_area': {
        'width': '100%', 'height': '60px', 'lineHeight': '60px',
        'borderWidth': '2px', 'borderStyle': 'solid', 'borderRadius': '12px',
        'borderColor': '#00ffff', 'textAlign': 'center', 'marginBottom': '20px',
        'fontFamily': 'Consolas, monospace', 'fontWeight': 'bold',
        'color': '#00ffff', 'background': 'linear-gradient(145deg, #0d0d0d, #121212)',
        'boxShadow': '0 0 15px #00ffffa0', 'cursor': 'pointer', 'transition': 'all 0.3s ease'
    },
    'table_style': {
        'backgroundColor': '#0a0a0a', 'borderRadius': '12px',
        'boxShadow': '0 0 20px #00ffff90', 'padding': '10px',
        'maxHeight': '520px', 'overflowY': 'auto', 'fontSize': '14px',
        'overflowX': 'auto'  # allow horizontal scroll if needed
    },
    'table_header': {
        'backgroundColor': '#004d4d', 'color': '#00ffff',
        'fontFamily': 'Consolas, monospace', 'fontWeight': 'bold',
        'fontSize': '15px', 'borderBottom': '2px solid #00cccc',
        'textTransform': 'uppercase', 'letterSpacing': '1.5px',
    },
    'table_cell': {
        'backgroundColor': '#111111', 'color': '#00ffff',
        'fontFamily': 'Consolas, monospace', 'textAlign': 'center',
        'minWidth': '90px', 'whiteSpace': 'nowrap', 'padding': '6px 10px',
    },
    'summary_style': {
        'whiteSpace': 'pre-wrap', 'fontFamily': 'Consolas, monospace',
        'color': '#00ff99', 'backgroundColor': '#111111', 'padding': '20px',
        'height': '520px', 'overflowY': 'auto', 'borderRadius': '12px',
        'border': '2px solid #00ff99', 'fontSize': '15px',
        'lineHeight': '1.4', 'userSelect': 'text',
        'boxShadow': '0 0 20px #00ff99aa',
        'minWidth': '250px'
    }
}

# === Layout ===
app.layout = dbc.Container([
    # Header
    dbc.Row([
        dbc.Col(
            html.Div([
                html.Img(src="/assets/logo.png", height="100px", style={'display': 'block', 'margin': '0 auto'}),
                html.H1("Side by Side", style={
                    "color": "#00ffff", "fontFamily": "Consolas, monospace",
                    "textShadow": "0 0 1px #00ffff, 0 0 20px #00ffff",
                    "fontWeight": "900", "letterSpacing": "2px", "fontSize": "2.6rem",
                    "textAlign": "center",
                    "marginBottom": "0"
                }),
                html.Div("by New Well Technologies", style={
                    "color": "#aaa", "fontFamily": "Consolas, monospace",
                    "fontSize": "0.9rem", "marginTop": "0", "textAlign": "center"
                }),
            ]),
            width=12
        )
    ], style={"marginTop": "25px", "marginBottom": "35px"}),

    # Main content row (3-column layout)
    dbc.Row([
        # MWD Table (left)
        dbc.Col([
            html.H4("Upload MWD Survey File", style={"color": "#00b3b3", "fontFamily": "Consolas, monospace"}),
            dcc.Upload(
                id='upload-mwd',
                children=html.Div(['Drag and Drop or ', html.A('Select MWD File')]),
                style=CUSTOM_STYLES['upload_area'],
                multiple=False,
            ),
            html.Div(
                dash_table.DataTable(
                    id='mwd-table',
                    columns=[{"name": c, "id": c} for c in ['MD', 'INC', 'AZ']],
                    data=[], style_header=CUSTOM_STYLES['table_header'],
                    style_cell=CUSTOM_STYLES['table_cell'],
                    style_table=CUSTOM_STYLES['table_style'],
                    style_data_conditional=[], page_action='none',
                    fixed_rows={'headers': True},
                ),
                style={'height': '520px', 'overflowY': 'auto', 'overflowX': 'auto'}
            )
        ], width=4),  # 1/3 of row

        # DD Table (middle)
        dbc.Col([
            html.H4("Upload DD Survey File", style={"color": "#00b3b3", "fontFamily": "Consolas, monospace"}),
            dcc.Upload(
                id='upload-dd',
                children=html.Div(['Drag and Drop or ', html.A('Select DD File')]),
                style=CUSTOM_STYLES['upload_area'],
                multiple=False,
            ),
            html.Div(
                dash_table.DataTable(
                    id='dd-table',
                    columns=[{"name": c, "id": c} for c in ['MD', 'INC', 'AZ']],
                    data=[], style_header=CUSTOM_STYLES['table_header'],
                    style_cell=CUSTOM_STYLES['table_cell'],
                    style_table=CUSTOM_STYLES['table_style'],
                    style_data_conditional=[], page_action='none',
                    fixed_rows={'headers': True},
                ),
                style={'height': '520px', 'overflowY': 'auto', 'overflowX': 'auto'}
            )
        ], width=4),  # 1/3 of row

        # Comparison Summary (right)
        dbc.Col([
            html.H4("Comparison Summary", style={"color": "#00ff99", "fontFamily": "Consolas, monospace"}),
            html.Div(id='summary', style=CUSTOM_STYLES['summary_style'])
        ], width=2),  # 1/3 of row
    ],
        align="start",
        style={'gap': '10px'}
    ),

    # === Mismatch rows container and copy buttons ===
    dbc.Row([
        dbc.Col([
            html.H4("Mismatched Rows", style={"color": "#ff5555", "fontFamily": "Consolas, monospace", "marginTop": "20px"}),
            dash_table.DataTable(
                id='mismatched-table',
                columns=[
                    {"name": "Index", "id": "Index"},
                    {"name": "MWD MD", "id": "MWD_MD"},
                    {"name": "MWD INC", "id": "MWD_INC"},
                    {"name": "MWD AZ", "id": "MWD_AZ"},
                    {"name": "DD MD", "id": "DD_MD"},
                    {"name": "DD INC", "id": "DD_INC"},
                    {"name": "DD AZ", "id": "DD_AZ"},
                ],
                data=[],
                style_header=CUSTOM_STYLES['table_header'],
                style_cell=CUSTOM_STYLES['table_cell'],
                style_table={'maxHeight': '300px', 'overflowY': 'auto', 'boxShadow': '0 0 20px #ff555590'},
                page_action='none',
                fixed_rows={'headers': True},
            ),
            dbc.ButtonGroup([
                dbc.Button("Copy MWD Mismatches", id='copy-mwd-btn', color="danger", className="me-2"),
                dbc.Button("Copy DD Mismatches", id='copy-dd-btn', color="danger")
            ], style={'marginTop': '10px'}),
            # Stores hold CSV text for copying
            dcc.Store(id='store-mwd-mismatch'),
            dcc.Store(id='store-dd-mismatch'),

            # Dummy divs for clientside callback outputs
            html.Div(id='dummy-output-mwd', style={'display': 'none'}),
            html.Div(id='dummy-output-dd', style={'display': 'none'}),
        ], width=12)
    ])

], fluid=True)


# === Main callback for parsing and updating tables + mismatch data ===
@app.callback(
    Output('mwd-table', 'data'),
    Output('mwd-table', 'style_data_conditional'),
    Output('dd-table', 'data'),
    Output('dd-table', 'style_data_conditional'),
    Output('summary', 'children'),
    Output('mismatched-table', 'data'),
    Output('mismatched-table', 'style_data_conditional'),
    Output('store-mwd-mismatch', 'data'),
    Output('store-dd-mismatch', 'data'),
    Input('upload-mwd', 'contents'),
    Input('upload-mwd', 'filename'),
    Input('upload-dd', 'contents'),
    Input('upload-dd', 'filename'),
)
def update_tables(mwd_contents, mwd_filename, dd_contents, dd_filename):
    if not mwd_contents or not dd_contents:
        return [], [], [], [], "📊 Upload both MWD and DD survey files to compare.", [], [], None, None

    try:
        mwd_df = parse_survey_file(mwd_contents, mwd_filename, "MWD")
        dd_df = parse_survey_file(dd_contents, dd_filename, "DD")
    except Exception as e:
        return [], [], [], [], f"❌ Error parsing files:\n{str(e)}", [], [], None, None

    style_cond_mwd = []
    style_cond_dd = []
    style_cond_mismatch = []
    min_len = min(len(mwd_df), len(dd_df))
    mismatches = {"MD": 0, "INC": 0, "AZ": 0, "rows": 0}

    mismatch_rows = []
    mwd_mismatch_csv = []
    dd_mismatch_csv = []

    for i in range(min_len):
        row_mismatch = False
        mismatch_columns = []
        for col in ['MD', 'INC', 'AZ']:
            val_left = pd.to_numeric(mwd_df.at[i, col], errors='coerce')
            val_right = pd.to_numeric(dd_df.at[i, col], errors='coerce')
            if pd.isna(val_left) or pd.isna(val_right) or round(val_left, 2) != round(val_right, 2):
                mismatches[col] += 1
                row_mismatch = True
                mismatch_columns.append(col)

                color = {'MD': '#d22e2e', 'INC': '#d27c2e', 'AZ': '#7c2ed2'}[col]

                style_cond_mwd.append({
                    'if': {'row_index': i, 'column_id': col},
                    'backgroundColor': color,
                    'color': '#fff',
                    'fontWeight': 'bold',
                })
                style_cond_dd.append({
                    'if': {'row_index': i, 'column_id': col},
                    'backgroundColor': color,
                    'color': '#fff',
                    'fontWeight': 'bold',
                })
        if row_mismatch:
            mismatches['rows'] += 1

            # Add mismatch row for container
            mismatch_rows.append({
                "Index": i + 1,
                "MWD_MD": mwd_df.at[i, 'MD'],
                "MWD_INC": mwd_df.at[i, 'INC'],
                "MWD_AZ": mwd_df.at[i, 'AZ'],
                "DD_MD": dd_df.at[i, 'MD'],
                "DD_INC": dd_df.at[i, 'INC'],
                "DD_AZ": dd_df.at[i, 'AZ'],
            })

            # Add styles for mismatch container
            for col in mismatch_columns:
                # Column IDs in mismatch table: MWD_*, DD_*
                mwd_col = f"MWD_{col}"
                dd_col = f"DD_{col}"
                color = {'MD': '#d22e2e', 'INC': "#e88325", 'AZ': '#7c2ed2'}[col]

                style_cond_mismatch.append({
                    'if': {'row_index': len(mismatch_rows)-1, 'column_id': mwd_col},
                    'backgroundColor': color,
                    'color': '#fff',
                    'fontWeight': 'bold',
                })
                style_cond_mismatch.append({
                    'if': {'row_index': len(mismatch_rows)-1, 'column_id': dd_col},
                    'backgroundColor': color,
                    'color': '#fff',
                    'fontWeight': 'bold',
                })

            mwd_mismatch_csv.append([mwd_df.at[i, 'MD'], mwd_df.at[i, 'INC'], mwd_df.at[i, 'AZ']])
            dd_mismatch_csv.append([dd_df.at[i, 'MD'], dd_df.at[i, 'INC'], dd_df.at[i, 'AZ']])

    accuracy = 100 - (mismatches['rows'] / min_len * 100) if min_len > 0 else 0

    summary = (
        f"📊 Survey Comparison Summary\n"
        f"────────────────────────────\n"
        f"Total Rows Compared: {min_len}\n"
        f"Row Mismatches: {mismatches['rows']}\n"
        f"MD Mismatches: {mismatches['MD']}\n"
        f"INC Mismatches: {mismatches['INC']}\n"
        f"AZ Mismatches: {mismatches['AZ']}\n"
        f"Accuracy: {accuracy:.2f}%\n"
    )

    mwd_csv_text = "MD,INC,AZ\n" + "\n".join([",".join(row) for row in mwd_mismatch_csv]) if mwd_mismatch_csv else ""
    dd_csv_text = "MD,INC,AZ\n" + "\n".join([",".join(row) for row in dd_mismatch_csv]) if dd_mismatch_csv else ""

    return (
        mwd_df.to_dict('records'), style_cond_mwd,
        dd_df.to_dict('records'), style_cond_dd,
        summary,
        mismatch_rows, style_cond_mismatch,
        mwd_csv_text, dd_csv_text
    )


# === Clientside callbacks for copy buttons ===
app.clientside_callback(
    """
    function(n_clicks, csv_text) {
        if (n_clicks && csv_text) {
            navigator.clipboard.writeText(csv_text)
                .then(() => {
                    alert('MWD mismatches copied to clipboard!');
                })
                .catch(err => {
                    alert('Failed to copy MWD mismatches: ' + err);
                });
        }
        return '';
    }
    """,
    Output('dummy-output-mwd', 'children'),
    Input('copy-mwd-btn', 'n_clicks'),
    State('store-mwd-mismatch', 'data'),
    prevent_initial_call=True
)

app.clientside_callback(
    """
    function(n_clicks, csv_text) {
        if (n_clicks && csv_text) {
            navigator.clipboard.writeText(csv_text)
                .then(() => {
                    alert('DD mismatches copied to clipboard!');
                })
                .catch(err => {
                    alert('Failed to copy DD mismatches: ' + err);
                });
        }
        return '';
    }
    """,
    Output('dummy-output-dd', 'children'),
    Input('copy-dd-btn', 'n_clicks'),
    State('store-dd-mismatch', 'data'),
    prevent_initial_call=True
)


if __name__ == '__main__':
    app.run(debug=True)
