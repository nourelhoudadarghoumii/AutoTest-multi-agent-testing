class Rectangle:
    """A rectangle with validated dimensions."""

    def __init__(self, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("dimensions must be positive")
        self.width = width
        self.height = height

    def area(self):
        return self.width * self.height

    def perimeter(self):
        return 2 * (self.width + self.height)

    def scale(self, factor):
        """Return a new Rectangle scaled by factor."""
        if factor <= 0:
            raise ValueError("factor must be positive")
        return Rectangle(self.width * factor, self.height * factor)
