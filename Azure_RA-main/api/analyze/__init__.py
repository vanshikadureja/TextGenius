import json
import logging
import os
import urllib.request
import urllib.error
import time

import azure.functions as func

ENDPOINT = os.environ.get("LANGUAGE_ENDPOINT", "").rstrip("/")
KEY = os.environ.get("LANGUAGE_KEY", "")

API_VERSION = "2023-04-01"
HEADERS = {
    "Content-Type": "application/json",
    "Ocp-Apim-Subscription-Key": KEY,
}


def main(req: func.HttpRequest) -> func.HttpResponse:

    if not ENDPOINT or not KEY:
        return func.HttpResponse(
            json.dumps({
                "error": "Missing LANGUAGE_ENDPOINT or LANGUAGE_KEY"
            }),
            status_code=500,
            mimetype="application/json",
        )

    try:
        body = req.get_json()
    except:
        body = {}

    text = body.get("text", "").strip()

    if not text:
        return func.HttpResponse(
            json.dumps({"error": "Text is required"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        language = detect_language(text)
        pii = pii_redaction(text)
        summary = abstractive_summary(text)

        result = {
            "language": language,
            "piiRedactedText": pii,
            "summary": summary
        }

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logging.exception(e)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


def detect_language(text):

    url = f"{ENDPOINT}/language/:analyze-text?api-version={API_VERSION}"

    payload = {
        "kind": "LanguageDetection",
        "analysisInput": {
            "documents": [
                {
                    "id": "1",
                    "text": text
                }
            ]
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=HEADERS,
        method="POST"
    )

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())

    return data["results"]["documents"][0]["detectedLanguage"]["name"]


def pii_redaction(text):

    url = f"{ENDPOINT}/language/:analyze-text?api-version={API_VERSION}"

    payload = {
        "kind": "PiiEntityRecognition",
        "analysisInput": {
            "documents": [
                {
                    "id": "1",
                    "language": "en",
                    "text": text
                }
            ]
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=HEADERS,
        method="POST"
    )

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())

    return data["results"]["documents"][0]["redactedText"]


def abstractive_summary(text):

    url = f"{ENDPOINT}/language/analyze-text/jobs?api-version={API_VERSION}"

    payload = {
        "displayName": "summary",
        "analysisInput": {
            "documents": [
                {
                    "id": "1",
                    "language": "en",
                    "text": text
                }
            ]
        },
        "tasks": [
            {
                "kind": "AbstractiveSummarization"
            }
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=HEADERS,
        method="POST"
    )

    response = urllib.request.urlopen(req)

    operation_url = response.headers["operation-location"]

    while True:

        req = urllib.request.Request(
            operation_url,
            headers={
                "Ocp-Apim-Subscription-Key": KEY
            }
        )

        result = urllib.request.urlopen(req)

        data = json.loads(result.read().decode())

        if data["status"] == "succeeded":

            return data["tasks"]["items"][0]["results"]["documents"][0]["summaries"][0]["text"]

        elif data["status"] == "failed":
            raise Exception("Summarization failed")

        time.sleep(2)
