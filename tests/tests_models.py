import unittest

from clickupython import models


class TestCustomFieldValue(unittest.TestCase):
    def test_people_type_value(self):
        # Arrange
        value = [
            {
                "id": 94583895,
                "username": "someone",
                "profilePicture": "https://example.com/pictures/94583895_E60.jpg",
            }
        ]

        # Act
        custom_field = models.CustomField(id="abc", name="People field", type="users", value=value)

        # Assert
        self.assertEqual(len(custom_field.value), 1)
        self.assertEqual(custom_field.value[0].id, 94583895)
        self.assertEqual(custom_field.value[0].username, "someone")
