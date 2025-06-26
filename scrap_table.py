import json
import uuid
import os
from playwright.sync_api import sync_playwright
import boto3

def lambda_handler(event, context):
    url = "https://ultimosismo.igp.gob.pe/ultimo-sismo/sismos-reportados"
    selector = "table.table.table-hover.table-bordered.table-light.border-white.w-100"

    # ——— Scraping con Playwright ———
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(selector, timeout=10_000)

        # extraer encabezados
        headers = [h.inner_text().strip() for h in page.query_selector_all(f"{selector} thead th")]

        # extraer filas
        rows = []
        for idx, tr in enumerate(page.query_selector_all(f"{selector} tbody tr"), start=1):
            cells = tr.query_selector_all("td")
            obj = { headers[i]: cells[i].inner_text().strip() if i < len(cells) else ""
                    for i in range(len(headers)) }
            obj["#"] = idx
            obj["id"] = str(uuid.uuid4())
            rows.append(obj)

        browser.close()

    # ——— Guardar en DynamoDB ———
    dynamodb = boto3.resource("dynamodb")
    table_name = os.getenv("TABLE_NAME", "TablaWebScrapping")
    table = dynamodb.Table(table_name)

    # Vaciamos la tabla antes de meter datos nuevos
    scan = table.scan(ProjectionExpression="id")
    with table.batch_writer() as batch:
        for item in scan.get("Items", []):
            batch.delete_item(Key={"id": item["id"]})

    # Insertar filas frescas
    for item in rows:
        table.put_item(Item=item)

    # ——— Respuesta HTTP ———
    return {
        "statusCode": 200,
        "headers": { "Content-Type": "application/json" },
        "body": json.dumps(rows, ensure_ascii=False)
    }
