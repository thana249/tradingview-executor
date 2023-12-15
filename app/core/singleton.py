# Python code for implementing the Singleton design pattern.

class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        """
        This method overrides the __call__ method of the metaclass.
        It ensures that only one instance of the class is created and returned.

        Args:
            cls: The class being instantiated.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            The instance of the class.
        """
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
