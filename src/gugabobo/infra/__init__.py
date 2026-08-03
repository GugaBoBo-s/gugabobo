import os

# litellm fetches a remote model price map on import unless this is already set,
# which blocks startup for the full 5 second HTTP timeout on restricted egress.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
