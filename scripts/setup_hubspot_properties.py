from pipeline.hubspot_client import create_property_if_missing

COMPANY_PROPERTIES = [
    {
        "name": "bites_tier",
        "label": "Bites Tier",
        "type": "enumeration",
        "fieldType": "select",
        "groupName": "companyinformation",
        "options": [
            {"label": "Tier 1", "value": "Tier 1"},
            {"label": "Tier 2", "value": "Tier 2"},
            {"label": "Tier 3", "value": "Tier 3"},
        ],
    },
    {
        "name": "site_count",
        "label": "Site Count",
        "type": "number",
        "fieldType": "number",
        "groupName": "companyinformation",
    },
    {
        "name": "governance_model",
        "label": "Governance Model",
        "type": "enumeration",
        "fieldType": "select",
        "groupName": "companyinformation",
        "options": [
            {"label": "Franchise", "value": "Franchise"},
            {"label": "Corporate", "value": "Corporate"},
            {"label": "Mixed", "value": "Mixed"},
        ],
    },
    {
        "name": "disqualified",
        "label": "Disqualified",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "groupName": "companyinformation",
        "options": [
            {"label": "True", "value": "true"},
            {"label": "False", "value": "false"},
        ],
    },
]

if __name__ == "__main__":
    for prop in COMPANY_PROPERTIES:
        result = create_property_if_missing("companies", prop)
        print(f"{prop['name']}: ok")
