from pipeline.hubspot_client import create_schema_if_missing

QSR_SIGNAL_SCHEMA = {
    "name": "qsr_signal",
    "labels": {"singular": "QSR Signal", "plural": "QSR Signals"},
    "primaryDisplayProperty": "signal_summary",
    "requiredProperties": ["signal_type", "signal_date"],
    "searchableProperties": ["source_activity_nr", "source_citation_id"],
    "properties": [
        {"name": "signal_summary", "label": "Signal Summary", "type": "string", "fieldType": "text"},
        {
            "name": "signal_type",
            "label": "Signal Type",
            "type": "enumeration",
            "fieldType": "select",
            "options": [
                {"label": "Complaint", "value": "Complaint"},
                {"label": "Accident", "value": "Accident"},
                {"label": "Fat/Cat", "value": "Fat/Cat"},
                {"label": "Violation", "value": "Violation"},
                {"label": "Hiring", "value": "Hiring"},
            ],
        },
        {"name": "signal_date", "label": "Signal Date", "type": "date", "fieldType": "date"},
        {"name": "source_url", "label": "Source URL", "type": "string", "fieldType": "text"},
        {"name": "penalty_amount", "label": "Penalty Amount", "type": "number", "fieldType": "number"},
        {"name": "severity", "label": "Severity/Classification", "type": "string", "fieldType": "text"},
        {"name": "description", "label": "Description", "type": "string", "fieldType": "textarea"},
        {"name": "source_activity_nr", "label": "Source Activity Nr (OSHA)", "type": "string", "fieldType": "text"},
        {"name": "source_citation_id", "label": "Source Citation ID (OSHA)", "type": "string", "fieldType": "text"},
    ],
    "associatedObjects": ["COMPANY"],
}

if __name__ == "__main__":
    result = create_schema_if_missing(QSR_SIGNAL_SCHEMA)
    print(f"qsr_signal schema ok - objectTypeId {result['objectTypeId']}")
