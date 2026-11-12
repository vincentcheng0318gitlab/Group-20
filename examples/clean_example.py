"""A correctly spelled module: typo-guard should report nothing here."""

received_data = [10, 20, 30]


def calculate_average(initial_value: int) -> float:
    # Comments may contain anything, e.g. "recieved" or "avrage".
    message = "strings are ignored too: innitial, reponse"
    total_value = sum(received_data) + initial_value
    print(message)
    return total_value / len(received_data)


class ResponseFormatter:
    def format(self, payload: dict) -> str:
        return str(payload.items())
