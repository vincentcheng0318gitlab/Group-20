import random

def ganerate_randm_num(min_value: float = 0.0, max_value: float = 1.0) -> float:
    """
    Generates a random floating-point number between min_value and max_value.
    """
    return random.uniform(min_value, max_value)

print(ganerate_randm_num())
print(ganerate_randm_num(1, 100)) 
