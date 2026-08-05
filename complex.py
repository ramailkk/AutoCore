# complex_processor.py
"""
Advanced Python Concepts Demo:
- Decorators, Context Managers, Generators
- Async/Await, Threading
- Metaclasses, Descriptors
- Type Hints, Dataclasses
- Custom Exceptions, Enums
- Functional Programming
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from functools import lru_cache, partial, reduce
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ENUMS & EXCEPTIONS ====================

class Status(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()

class ProcessingError(Exception):
    """Custom exception for processing errors"""
    pass

# ==================== DECORATORS ====================

def timer(func: Callable) -> Callable:
    """Decorator to measure execution time"""
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

def retry(max_attempts: int = 3, delay: float = 1.0):
    """Decorator to retry failed operations"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(f"Attempt {attempt+1} failed: {e}. Retrying...")
                    time.sleep(delay * (attempt + 1))
        return wrapper
    return decorator

def log_execution(func: Callable) -> Callable:
    """Decorator to log function calls"""
    def wrapper(*args, **kwargs):
        logger.info(f"Executing {func.__name__}")
        result = func(*args, **kwargs)
        logger.info(f"Completed {func.__name__}")
        return result
    return wrapper

# ==================== DESCRIPTOR ====================

class ValidatedAttribute:
    """Descriptor for validated attributes"""
    def __init__(self, name: str, validator: Callable):
        self.name = name
        self.validator = validator
        self.private_name = f"_{name}"
    
    def __get__(self, obj, objtype=None):
        return getattr(obj, self.private_name, None)
    
    def __set__(self, obj, value):
        if not self.validator(value):
            raise ValueError(f"Invalid value for {self.name}: {value}")
        setattr(obj, self.private_name, value)

# ==================== METACLASS ====================

class SingletonMeta(type):
    """Metaclass for singleton pattern"""
    _instances = {}
    _lock = threading.Lock()
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

# ==================== SINGLETON CLASS ====================

class ConfigManager(metaclass=SingletonMeta):
    """Configuration manager (singleton)"""
    def __init__(self):
        self._config = {}
    
    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)
    
    def to_dict(self) -> Dict:
        return self._config.copy()

# ==================== CONTEXT MANAGER ====================

@contextmanager
def timed_operation(name: str):
    """Context manager for timing operations"""
    start = time.perf_counter()
    logger.info(f"Starting {name}")
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info(f"{name} completed in {elapsed:.4f}s")

class ResourceManager:
    """Context manager for resource handling"""
    def __enter__(self):
        logger.info("Acquiring resource")
        self.resource = "resource_acquired"
        return self.resource
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.info("Releasing resource")
        if exc_type:
            logger.error(f"Error occurred: {exc_val}")
        return False

# ==================== DATA CLASS ====================

@dataclass
class DataPoint:
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

@dataclass
class ProcessResult:
    status: Status
    data: Any
    errors: List[str] = field(default_factory=list)
    processing_time: float = 0.0

# ==================== PROCESSOR CLASS ====================

class DataProcessor:
    """Main data processor with multiple features"""
    
    name = ValidatedAttribute("name", lambda x: isinstance(x, str) and len(x) > 0)
    
    def __init__(self, name: str):
        self.name = name
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._processed_count = 0
    
    @timer
    @retry(max_attempts=2)
    @log_execution
    def process(self, data: List[float]) -> ProcessResult:
        """Process numeric data with multiple operations"""
        if not data:
            return ProcessResult(Status.FAILED, None, ["Empty data"])
        
        try:
            with timed_operation("data_processing"):
                with ResourceManager() as resource:
                    logger.info(f"Using {resource}")
                    
                    # Calculate statistics
                    stats = self._calculate_stats(data)
                    
                    # Transform data
                    transformed = self._transform_data(data)
                    
                    # Detect anomalies
                    anomalies = self._detect_anomalies(data, stats['mean'], stats['std'])
                    
                    result = {
                        'stats': stats,
                        'transformed': transformed,
                        'anomalies': anomalies,
                        'processed_at': datetime.now().isoformat()
                    }
                    
                    self._processed_count += len(data)
                    
                    return ProcessResult(Status.COMPLETED, result)
                    
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            return ProcessResult(Status.FAILED, None, [str(e)])
    
    def _calculate_stats(self, data: List[float]) -> Dict:
        """Calculate statistical measures"""
        n = len(data)
        if n == 0:
            return {}
        
        mean = sum(data) / n
        variance = sum((x - mean) ** 2 for x in data) / n
        std = variance ** 0.5
        sorted_data = sorted(data)
        
        return {
            'count': n,
            'sum': sum(data),
            'mean': mean,
            'std': std,
            'variance': variance,
            'min': min(data),
            'max': max(data),
            'median': sorted_data[n // 2] if n % 2 else 
                     (sorted_data[n//2 - 1] + sorted_data[n//2]) / 2
        }
    
    def _transform_data(self, data: List[float]) -> List[float]:
        """Transform data (standardization)"""
        mean = sum(data) / len(data)
        std = (sum((x - mean) ** 2 for x in data) / len(data)) ** 0.5
        if std == 0:
            return data
        return [(x - mean) / std for x in data]
    
    def _detect_anomalies(self, data: List[float], mean: float, std: float, threshold: float = 3) -> List[int]:
        """Detect anomalies using z-score"""
        if std == 0:
            return []
        return [i for i, x in enumerate(data) if abs((x - mean) / std) > threshold]
    
    @lru_cache(maxsize=32)
    def cached_calculation(self, a: float, b: float) -> float:
        """Memoized calculation"""
        return a ** 2 + b ** 2
    
    def process_batch(self, batch_data: List[List[float]]) -> List[ProcessResult]:
        """Process batch of data"""
        results = []
        for data in batch_data:
            results.append(self.process(data))
        return results
    
    def get_stats(self) -> Dict:
        """Get processor statistics"""
        return {
            'processed_count': self._processed_count,
            'cache_size': len(self._cache)
        }

# ==================== GENERATORS ====================

def chunk_generator(data: List[Any], chunk_size: int):
    """Generator that yields chunks of data"""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]

def fibonacci_generator(n: int):
    """Generate Fibonacci sequence"""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

def prime_generator(limit: int):
    """Generate prime numbers"""
    def is_prime(num):
        if num < 2:
            return False
        for i in range(2, int(num ** 0.5) + 1):
            if num % i == 0:
                return False
        return True
    
    for num in range(2, limit + 1):
        if is_prime(num):
            yield num

# ==================== ASYNC FUNCTIONS ====================

async def async_processor(data: List[float], processor: DataProcessor) -> ProcessResult:
    """Process data asynchronously"""
    # Simulate async operation
    await asyncio.sleep(0.1)
    return processor.process(data)

async def async_batch_processor(batches: List[List[float]], processor: DataProcessor) -> List[ProcessResult]:
    """Process multiple batches asynchronously"""
    tasks = [async_processor(batch, processor) for batch in batches]
    return await asyncio.gather(*tasks)

# ==================== THREAD POOL ====================

class ThreadPool:
    """Simple thread pool for parallel execution"""
    def __init__(self, num_workers: int = 4):
        self.num_workers = num_workers
        self._queue: List[Callable] = []
        self._results: List[Any] = []
        self._lock = threading.Lock()
        self._stop = False
    
    def submit(self, func: Callable, *args, **kwargs) -> None:
        """Submit a task to the pool"""
        with self._lock:
            self._queue.append((func, args, kwargs))
    
    def process_all(self) -> List[Any]:
        """Process all tasks"""
        threads = []
        for _ in range(self.num_workers):
            t = threading.Thread(target=self._worker)
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
        
        return self._results
    
    def _worker(self):
        """Worker thread"""
        while True:
            with self._lock:
                if not self._queue:
                    break
                func, args, kwargs = self._queue.pop()
            
            try:
                result = func(*args, **kwargs)
                with self._lock:
                    self._results.append(result)
            except Exception as e:
                with self._lock:
                    self._results.append(e)

# ==================== UTILITY FUNCTIONS ====================

@timer
def expensive_calculation(n: int) -> int:
    """Expensive calculation with recursion"""
    if n <= 1:
        return n
    return expensive_calculation(n - 1) + expensive_calculation(n - 2)

def pipe(data: Any, *functions: Callable) -> Any:
    """Functional pipeline: pipe(data, f1, f2, f3)"""
    result = data
    for func in functions:
        result = func(result)
    return result

def compose(*functions: Callable) -> Callable:
    """Compose multiple functions: compose(f, g)(x) = f(g(x))"""
    return lambda x: reduce(lambda acc, f: f(acc), reversed(functions), x)

def filter_odd(data: List[int]) -> List[int]:
    """Filter odd numbers"""
    return [x for x in data if x % 2 == 0]

def multiply_by_2(data: List[int]) -> List[int]:
    """Multiply all numbers by 2"""
    return [x * 2 for x in data]

def square_numbers(data: List[int]) -> List[int]:
    """Square all numbers"""
    return [x ** 2 for x in data]

# ==================== MAIN DEMONSTRATION ====================

def main():
    """Demonstrate all features"""
    logger.info("=" * 60)
    logger.info("DEMONSTRATING COMPLEX PYTHON")
    logger.info("=" * 60)
    
    # 1. Singleton Config
    config1 = ConfigManager()
    config2 = ConfigManager()
    config1.set("debug", True)
    logger.info(f"Same instance? {config1 is config2}")
    logger.info(f"Config: {config2.get('debug')}")
    
    # 2. Data Processing
    processor = DataProcessor("MainProcessor")
    data = [1, 2, 3, 4, 5, 100, 6, 7, 8]  # 100 is anomaly
    
    result = processor.process(data)
    logger.info(f"Result status: {result.status}")
    if result.status == Status.COMPLETED:
        logger.info(f"Result data: {json.dumps(result.data, indent=2)}")
    
    # 3. Generators
    logger.info("Fibonacci numbers:")
    for num in fibonacci_generator(10):
        logger.info(f"  {num}")
    
    # 4. Functional Programming
    data_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    
    # Pipeline approach
    result_pipe = pipe(
        data_list,
        filter_odd,
        multiply_by_2,
        square_numbers
    )
    logger.info(f"Pipe result: {result_pipe}")
    
    # Compose approach
    composed = compose(square_numbers, multiply_by_2, filter_odd)
    logger.info(f"Composed result: {composed(data_list)}")
    
    # 5. Context Manager
    with timed_operation("sample_operation"):
        time.sleep(0.1)
        logger.info("Operation executed")
    
    # 6. LRU Cache
    logger.info(f"Memoized result: {processor.cached_calculation(5, 3)}")
    logger.info(f"Memoized result (cached): {processor.cached_calculation(5, 3)}")
    
    # 7. Async Processing
    logger.info("Running async demo...")
    
    async def async_demo():
        batches = [data[i:i+3] for i in range(0, len(data), 3)]
        results = await async_batch_processor(batches, processor)
        for r in results:
            logger.info(f"Async result: {r.status}")
    
    try:
        asyncio.run(async_demo())
    except RuntimeError:
        # Already in event loop
        pass
    
    # 8. Threading
    logger.info("Running thread pool demo...")
    pool = ThreadPool(num_workers=2)
    
    for i in range(5):
        pool.submit(expensive_calculation, i + 30)
    
    results = pool.process_all()
    logger.info(f"Thread pool results: {results}")
    
    logger.info("=" * 60)
    logger.info("DEMONSTRATION COMPLETE")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()