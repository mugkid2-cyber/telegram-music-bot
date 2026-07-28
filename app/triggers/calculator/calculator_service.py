"""
Сервис для безопасного вычисления математических выражений.
"""
import re
import math
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CalculatorService:
    """Безопасный калькулятор для вычисления математических выражений."""

    # Разрешенные математические функции
    ALLOWED_FUNCTIONS = {
        'abs': abs,
        'round': round,
        'sqrt': math.sqrt,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'log': math.log,
        'log10': math.log10,
        'exp': math.exp,
        'pow': pow,
        'pi': math.pi,
        'e': math.e,
    }

    # Паттерн для определения математического выражения
    MATH_PATTERN = re.compile(
        r'^[\d\s\+\-\*\/\(\)\.\^\%]+$|'  # Простые арифметические операции
        r'\b(sin|cos|tan|sqrt|log|exp|abs|round|pow)\s*\(',  # Функции
        re.IGNORECASE
    )

    @classmethod
    def is_math_expression(cls, text: str) -> bool:
        """
        Проверяет, является ли текст математическим выражением.

        Args:
            text: Текст для проверки

        Returns:
            True если это математическое выражение
        """
        if not text or len(text.strip()) < 3:
            return False

        text = text.strip()

        # Должно содержать хотя бы один математический оператор или функцию
        has_operator = any(op in text for op in ['+', '-', '*', '/', '^', '%', '(', ')'])
        has_function = any(func in text.lower() for func in cls.ALLOWED_FUNCTIONS.keys())

        if not (has_operator or has_function):
            return False

        # Проверяем паттерн
        # Заменяем ^ на ** для Python
        test_text = text.replace('^', '**')

        # Убираем пробелы
        test_text = test_text.replace(' ', '')

        # Проверяем, что содержит только разрешенные символы
        allowed_chars = re.compile(r'^[\d\+\-\*\/\(\)\.\%\w]+$')
        if not allowed_chars.match(test_text):
            return False

        # Должно содержать хотя бы одну цифру
        if not re.search(r'\d', test_text):
            return False

        return True

    @classmethod
    def calculate(cls, expression: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Безопасно вычисляет математическое выражение.

        Args:
            expression: Математическое выражение

        Returns:
            Кортеж (результат, текст ошибки)
        """
        if not expression:
            return None, "Пустое выражение"

        try:
            # Подготавливаем выражение
            expr = expression.strip()

            # Заменяем ^ на ** для возведения в степень
            expr = expr.replace('^', '**')

            # Удаляем пробелы
            expr = expr.replace(' ', '')

            # Проверяем на опасные символы и ключевые слова
            dangerous_keywords = ['import', '__', 'exec', 'eval', 'compile', 'open', 'file']
            for keyword in dangerous_keywords:
                if keyword in expr.lower():
                    return None, "Обнаружены запрещенные символы"

            # Создаем безопасное окружение для eval
            safe_dict = {
                '__builtins__': {},
                **cls.ALLOWED_FUNCTIONS
            }

            # Вычисляем
            result = eval(expr, safe_dict, {})

            # Проверяем результат
            if isinstance(result, (int, float)):
                # Округляем до 10 знаков после запятой для избежания floating point ошибок
                if isinstance(result, float):
                    result = round(result, 10)
                return result, None
            else:
                return None, "Неверный тип результата"

        except ZeroDivisionError:
            return None, "Деление на ноль"
        except ValueError as e:
            return None, f"Математическая ошибка: {str(e)}"
        except SyntaxError:
            return None, "Синтаксическая ошибка в выражении"
        except NameError as e:
            return None, f"Неизвестная функция или переменная"
        except Exception as e:
            logger.error(f"Unexpected error in calculation: {e}")
            return None, "Ошибка при вычислении"

    @classmethod
    def format_result(cls, result: float) -> str:
        """
        Форматирует результат для отображения.

        Args:
            result: Числовой результат

        Returns:
            Отформатированная строка
        """
        # Если целое число - выводим без дробной части
        if isinstance(result, float) and result.is_integer():
            return str(int(result))

        # Иначе выводим с удалением лишних нулей
        formatted = f"{result:.10f}".rstrip('0').rstrip('.')
        return formatted
