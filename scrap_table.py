import os
import json
import uuid
import asyncio
import boto3
from playwright.async_api import async_playwright

async def _fetch_table():
    url = "https://sgonorte.bomberosperu.gob.pe/24horas/?criterio=/"
    selector = "table"  # la única tabla de interés

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector(selector, timeout=10_000)

        # Encabezados
        headers = await page.eval_on_selector_all(
            f"{selector} thead th",
            "ths => ths.map(th => th.innerText.trim())"
        )
        # Filas
        data = []
        rows = await page.query_selector_all(f"{selector} tbody tr")
        for idx, tr in enumerate(rows, start=1):
            cells = await tr.query_selector_all("td")
            row = {}
            for i, h in enumerate(headers):
                text = await cells[i].inner_text() if i < len(cells) else ""
                row[h] = text.strip()
            row["#"] = idx
            row["id"] = str(uuid.uuid4())
            data.append(row)

        await browser.close()
    return data

def lambda_handler(event, context):
    # 1) Scrape dinámico
    data = asyncio.get_event_loop().run_until_complete(_fetch_table())

    # 2) Guardar en DynamoDB
    table_name = os.environ["TABLE_NAME"]
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    # vaciar tabla
    scan = table.scan(ProjectionExpression="id")
    with table.batch_writer() as batch:
        for item in scan.get("Items", []):
            batch.delete_item(Key={"id": item["id"]})

    # insertar nuevos
    for item in data:
        table.put_item(Item=item)

    # 3) Devolver JSON
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data, ensure_ascii=False)
    }
