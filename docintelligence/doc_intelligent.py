"""
This code sample shows Prebuilt Layout operations with the Azure AI Document Intelligence client library.
The async versions of the samples require Python 3.8 or later.

To learn more, please visit the documentation - Quickstart: Document Intelligence (formerly Form Recognizer) SDKs
https://learn.microsoft.com/azure/ai-services/document-intelligence/quickstarts/get-started-sdks-rest-api?pivots=programming-language-python
"""

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
import json

"""
Remember to remove the key from your code when you're done, and never post it publicly. For production, use
secure methods to store and access your credentials. For more information, see 
https://docs.microsoft.com/en-us/azure/cognitive-services/cognitive-services-security?tabs=command-line%2Ccsharp#environment-variables-and-application-configuration
"""
endpoint = "https://avalandformrecognision.cognitiveservices.azure.com/"
key = "98d9a0543e71417e94fad5ba36e55582"

# sample document
#formUrl = "https://raw.githubusercontent.com/Azure-Samples/cognitive-services-REST-api-samples/master/curl/form-recognizer/sample-layout.pdf"
blob_sas_url ="https://docintstorageavaland.blob.core.windows.net/salesmemo/Memo1.pdf?sp=r&st=2026-01-20T02:54:11Z&se=2026-02-13T11:09:11Z&spr=https&sv=2024-11-04&sr=b&sig=f4JzhJQN16X7BHHQZ8voVgS3Fjpr3WM5TW2KukJOi5o%3D"
document_intelligence_client  = DocumentIntelligenceClient(
    endpoint=endpoint, credential=AzureKeyCredential(key)
)

poller = document_intelligence_client.begin_analyze_document(
    "prebuilt-layout", AnalyzeDocumentRequest(url_source=blob_sas_url)
)
result = poller.result()

#From AnalyzeResult to JSON and Store the result 
with open("output.json", "w", encoding="utf-8") as f:
    json.dump(result.as_dict(), f, ensure_ascii=False, indent=2)

print("----Layout Analysis----")

for idx, style in enumerate(result.styles):
    print(
        "Document contains {} content".format(
         "handwritten" if style.is_handwritten else "no handwritten"
        )
    )

for page in result.pages:
    for line_idx, line in enumerate(page.lines):
        print(
         "...Line # {} has text content '{}'".format(
        line_idx,
        line.content
        )
    )

    if page.selection_marks:
        for selection_mark in page.selection_marks:
            print(
                "...Selection mark is '{}' and has a confidence of {}".format(
                    selection_mark.state,
                    selection_mark.confidence
                )
            )


for table_idx, table in enumerate(result.tables):
    print(
        "Table # {} has {} rows and {} columns".format(
        table_idx, table.row_count, table.column_count
        )
    )
        
    for cell in table.cells:
        print(
            "...Cell[{}][{}] has content '{}'".format(
            cell.row_index,
            cell.column_index,
            cell.content
            )
        )

print("----------------------------------------")
#Check pagenumber
print ("Document contains {} pages".format(len(result.pages)))

