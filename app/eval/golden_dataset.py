"""
Golden test set for evaluating retrieval quality.
Each entry: a query (representing a job requirement) and the chunk_id(s)
we've manually determined ARE the correct/relevant resume chunk(s) for it,
verified against the actual embedded chunk text (not just context fields).
"""

RETRIEVAL_GOLDEN_SET = [
    {
        "query": "React frontend development",
        "correct_chunk_ids": ["projects_001"],
    },
    {
        "query": "machine learning model development",
        "correct_chunk_ids": ["professional_experience_001"],
    },
    {
        "query": "RESTful API development",
        "correct_chunk_ids": ["professional_experience_005", "projects_006"],
    },
    {
        "query": "data preprocessing and analysis",
        "correct_chunk_ids": ["professional_experience_003"],
    },
    {
        "query": "team leadership",
        "correct_chunk_ids": ["skills_006"],
    },
    {
        "query": "time-series forecasting",
        "correct_chunk_ids": ["projects_002"],
    },
    {
        "query": "PostgreSQL database experience",
        "correct_chunk_ids": ["projects_001", "projects_006"],
    },
    {
        "query": "MERN stack development",
        "correct_chunk_ids": ["professional_experience_004"],
    },
]