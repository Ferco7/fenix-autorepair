class FenixError(Exception):
    """Excepción base para todos los errores del proyecto Fénix."""
    pass

class ValidationError(FenixError):
    """Excepción lanzada cuando la validación de entradas, esquemas o tipos falla."""
    pass

class DomainError(FenixError):
    """Excepción lanzada cuando ocurre una violación de las reglas de dominio o inventario."""
    pass
    
