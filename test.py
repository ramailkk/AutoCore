# simple_processor.py
"""
Simple data processing utilities
"""

def add(a: float, b: float) -> float:
    """Add two numbers"""
    return a + b

def multiply(a: float, b: float) -> float:
    """Multiply two numbers"""
    return a * b

def square(n: float) -> float:
    """Square a number"""
    return n ** 2

def is_even(n: int) -> bool:
    """Check if number is even"""
    return n % 2 == 0

def process_numbers(numbers: list) -> dict:
    """Process a list of numbers"""
    if not numbers:
        return {"error": "Empty list"}
    
    total = sum(numbers)
    count = len(numbers)
    average = total / count
    
    return {
        "count": count,
        "sum": total,
        "average": average,
        "max": max(numbers),
        "min": min(numbers),
        "even_count": len([n for n in numbers if is_even(n)])
    }

def main():
    """Test the functions"""
    numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    
    print(f"Numbers: {numbers}")
    print(f"Sum: {add(sum(numbers), 0)}")
    print(f"Average: {process_numbers(numbers)['average']}")
    print(f"Even numbers: {[n for n in numbers if is_even(n)]}")
    print(f"Squares: {[square(n) for n in numbers]}")

if __name__ == "__main__":
    main()