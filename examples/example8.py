import random

def flip_cin() -> str:
    """Simulates flipping a fair coin."""
    return random.choice(["Heads", "Tails"])

# Example usage:
print(flip_cin())  # e.g., "Heads"
