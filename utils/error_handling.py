"""
Error Handling Utilities for QCraft

This module provides consistent error handling patterns across the codebase.

Author: QCraft Development Team
Date: October 1, 2025
"""

import logging
import functools
import traceback
from typing import Callable, Optional, Any, Type
from types import TracebackType

logger = logging.getLogger(__name__)


class QCraftError(Exception):
    """Base exception for QCraft errors."""
    pass


class ConfigurationError(QCraftError):
    """Configuration-related errors."""
    pass


class MappingError(QCraftError):
    """Mapping-related errors."""
    pass


class OptimizationError(QCraftError):
    """Optimization-related errors."""
    pass


class HardwareError(QCraftError):
    """Hardware integration errors."""
    pass


class EncryptionError(QCraftError):
    """Encryption/decryption errors."""
    pass


class ValidationError(QCraftError):
    """Validation errors."""
    pass


def handle_errors(
    error_event_name: str,
    reraise: bool = True,
    default_return: Any = None,
    log_level: str = 'ERROR'
):
    """
    Decorator for consistent error handling.
    
    This decorator catches exceptions, logs them appropriately, and
    optionally re-raises them. It integrates with the logging system
    to provide consistent error reporting.
    
    Args:
        error_event_name: Event name for logging
        reraise: Whether to re-raise the exception after logging
        default_return: Value to return if exception caught and not re-raised
        log_level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    
    Example:
        >>> @handle_errors('mapping_error', reraise=True)
        ... def run_mapping(self, circuit, device_info):
        ...     # Implementation
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Get logger from self if available
                obj_logger = None
                if args and hasattr(args[0], 'logger'):
                    obj_logger = args[0].logger
                
                # Log the error
                error_data = {
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'function': func.__name__,
                    'module': func.__module__,
                }
                
                if obj_logger and hasattr(obj_logger, 'log_event'):
                    obj_logger.log_event(
                        error_event_name,
                        error_data,
                        level=log_level
                    )
                else:
                    log_func = getattr(logger, log_level.lower(), logger.error)
                    log_func(f"{error_event_name}: {error_data}")
                
                # Log traceback at debug level
                if log_level in ('ERROR', 'CRITICAL'):
                    logger.debug(f"Traceback for {error_event_name}:\n{traceback.format_exc()}")
                
                if reraise:
                    raise
                else:
                    return default_return
        
        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    *args,
    error_msg: str = "Operation failed",
    default_return: Any = None,
    log_errors: bool = True,
    **kwargs
) -> Any:
    """
    Safely execute a function with error handling.
    
    This is a functional alternative to the decorator for one-off operations.
    
    Args:
        func: Function to execute
        *args: Positional arguments for func
        error_msg: Error message to log
        default_return: Value to return on error
        log_errors: Whether to log errors
        **kwargs: Keyword arguments for func
    
    Returns:
        Function result or default_return on error
    
    Example:
        >>> result = safe_execute(
        ...     risky_operation,
        ...     arg1, arg2,
        ...     error_msg="Risky operation failed",
        ...     default_return={}
        ... )
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"{error_msg}: {e}")
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return default_return


class ErrorContext:
    """
    Context manager for error handling with cleanup.
    
    Example:
        >>> with ErrorContext("database_operation", cleanup_func=close_connection):
        ...     perform_database_operation()
    """
    
    def __init__(
        self,
        operation_name: str,
        cleanup_func: Optional[Callable] = None,
        reraise: bool = True,
        log_level: str = 'ERROR'
    ):
        """
        Initialize error context.
        
        Args:
            operation_name: Name of the operation for logging
            cleanup_func: Optional cleanup function to call on error
            reraise: Whether to re-raise exceptions
            log_level: Logging level for errors
        """
        self.operation_name = operation_name
        self.cleanup_func = cleanup_func
        self.reraise = reraise
        self.log_level = log_level
    
    def __enter__(self):
        """Enter context."""
        logger.debug(f"Starting operation: {self.operation_name}")
        return self
    
    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> bool:
        """Exit context with error handling."""
        if exc_type is not None:
            # Log error
            log_func = getattr(logger, self.log_level.lower(), logger.error)
            log_func(f"Error in {self.operation_name}: {exc_val}")
            logger.debug(f"Traceback:\n{''.join(traceback.format_tb(exc_tb))}")
            
            # Run cleanup
            if self.cleanup_func:
                try:
                    self.cleanup_func()
                    logger.debug(f"Cleanup completed for {self.operation_name}")
                except Exception as cleanup_error:
                    logger.error(f"Cleanup failed for {self.operation_name}: {cleanup_error}")
            
            # Return False to re-raise, True to suppress
            return not self.reraise
        
        logger.debug(f"Completed operation: {self.operation_name}")
        return False


def validate_input(
    condition: bool,
    error_message: str,
    exception_class: Type[Exception] = ValidationError
) -> None:
    """
    Validate input condition and raise exception if false.
    
    Args:
        condition: Condition to validate
        error_message: Error message if validation fails
        exception_class: Exception class to raise
    
    Raises:
        exception_class: If condition is False
    
    Example:
        >>> validate_input(
        ...     circuit is not None,
        ...     "Circuit cannot be None",
        ...     ValueError
        ... )
    """
    if not condition:
        logger.error(f"Validation failed: {error_message}")
        raise exception_class(error_message)


def retry_on_error(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator to retry function on specified exceptions.
    
    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts (seconds)
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch
    
    Example:
        >>> @retry_on_error(max_attempts=3, delay=1.0)
        ... def unstable_operation():
        ...     # Implementation
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import time
            
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts:
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                        )
            
            # All attempts failed, raise last exception
            raise last_exception
        
        return wrapper
    return decorator


class ErrorCollector:
    """
    Collect multiple errors without stopping execution.
    
    Useful for validation where you want to report all errors at once.
    
    Example:
        >>> collector = ErrorCollector()
        >>> collector.add_error("Invalid qubit count")
        >>> collector.add_error("Missing gate definition")
        >>> if collector.has_errors():
        ...     raise ValidationError(collector.get_summary())
    """
    
    def __init__(self):
        """Initialize error collector."""
        self.errors = []
    
    def add_error(self, error_message: str, context: Optional[dict] = None) -> None:
        """
        Add an error to the collection.
        
        Args:
            error_message: Error message
            context: Optional context dict
        """
        self.errors.append({
            'message': error_message,
            'context': context or {}
        })
    
    def has_errors(self) -> bool:
        """Check if any errors were collected."""
        return len(self.errors) > 0
    
    def get_errors(self) -> list:
        """Get list of all errors."""
        return self.errors
    
    def get_summary(self) -> str:
        """Get formatted summary of all errors."""
        if not self.errors:
            return "No errors"
        
        summary = f"Found {len(self.errors)} error(s):\n"
        for i, error in enumerate(self.errors, 1):
            summary += f"  {i}. {error['message']}\n"
            if error['context']:
                summary += f"     Context: {error['context']}\n"
        
        return summary
    
    def clear(self) -> None:
        """Clear all collected errors."""
        self.errors = []
    
    def raise_if_errors(self, exception_class: Type[Exception] = ValidationError) -> None:
        """
        Raise exception if errors were collected.
        
        Args:
            exception_class: Exception class to raise
        
        Raises:
            exception_class: If errors exist
        """
        if self.has_errors():
            raise exception_class(self.get_summary())


# Convenience functions for common error patterns
def log_and_raise(error_message: str, exception_class: Type[Exception] = QCraftError) -> None:
    """Log error and raise exception."""
    logger.error(error_message)
    raise exception_class(error_message)


def log_and_return(error_message: str, default_value: Any = None, log_level: str = 'WARNING') -> Any:
    """Log error and return default value."""
    log_func = getattr(logger, log_level.lower(), logger.warning)
    log_func(error_message)
    return default_value


def assert_not_none(value: Any, name: str) -> None:
    """Assert value is not None."""
    if value is None:
        raise ValidationError(f"{name} cannot be None")


def assert_positive(value: float, name: str) -> None:
    """Assert value is positive."""
    if value <= 0:
        raise ValidationError(f"{name} must be positive, got {value}")


def assert_in_range(value: float, min_val: float, max_val: float, name: str) -> None:
    """Assert value is in range."""
    if not (min_val <= value <= max_val):
        raise ValidationError(f"{name} must be in range [{min_val}, {max_val}], got {value}")
