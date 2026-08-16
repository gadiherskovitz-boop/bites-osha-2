# Persona tracks per signal type, per pipeline/HANDOFF plan.
# OSHA: 3 contacts, one senior contact per functional track (double up on
# another track if a given track's search comes back empty).
# Hiring: 2 contacts, prefer two L&D/Enablement leadership contacts; fall
# back to one L&D/Enablement + one HR/People leadership if only one
# L&D-track match exists.

OSHA_TRACKS = [
    {
        "track": "Operations",
        "level": "VP/COO",
        "title_keywords": ["VP Operations", "Vice President Operations", "COO", "Chief Operating Officer"],
        "seniority": ["vp", "c-suite"],
    },
    {
        "track": "Safety/EHS",
        "level": "Senior",
        "title_keywords": ["VP Safety", "Director of EHS", "Head of Safety", "Director of Safety", "EHS Director"],
        "seniority": ["vp", "director", "head", "c-suite"],
    },
    {
        "track": "L&D/Enablement",
        "level": "Head/CLO",
        "title_keywords": ["Head of L&D", "VP Learning and Development", "Chief Learning Officer", "Director of Training"],
        "seniority": ["vp", "director", "head", "c-suite"],
    },
]

HIRING_TRACKS = [
    {
        "track": "L&D/Enablement",
        "level": "Leadership",
        "title_keywords": ["Head of L&D", "VP Learning and Development", "Director of Training", "Chief Learning Officer"],
        "seniority": ["vp", "director", "head", "c-suite"],
    },
    {
        "track": "HR/People",
        "level": "Leadership",
        "title_keywords": ["VP People", "CHRO", "Chief Human Resources Officer", "VP Human Resources"],
        "seniority": ["vp", "c-suite"],
    },
]
