import sys

def review_guard(event, args):
    if event == "open" and args and "/outputs/final-pair-v91-heldout-" in str(args[0]):
        raise RuntimeError("REVIEW_362: real held-out access forbidden")
    if event == "import" and args and str(args[0]).split(".")[0] in {"mujoco", "torch", "torchvision", "openai", "anthropic"}:
        raise RuntimeError("REVIEW_362: physics/model import forbidden")
    if event == "socket.connect":
        raise RuntimeError("REVIEW_362: test network forbidden")
sys.addaudithook(review_guard)
