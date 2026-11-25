"""Helper functions for OT-2 protocol generation and other utilities."""

import csv
import os
import tempfile
import itertools
import ast

def generate_ot2_protocol(template_path, replacement_dict: dict) -> str:
    """Generates an OT-2 protocol by replacing variables in a template file."""

    # collect template contents and replace variables
    with template_path.open(mode="r") as f:
        edited_template_contents = f.read()
        for key in replacement_dict.keys():
            # print("KEY", key)
            edited_template_contents = edited_template_contents.replace("$" + key, str(replacement_dict[key]))
            # print(edited_template_contents)

    # write to another temp file
    output_file_name = None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as fp:
        fp.write(edited_template_contents.encode('utf-8'))
        output_file_name = fp.name

    return output_file_name


def collect_ot2_replacement_variables(payload: dict) -> dict:
    """Collects OT-2 replacement variables based on the payload."""

    replacement_dict = {}
    # if payload["ot2_node"] == "ot2_patrick":
    #     tip_box_location = payload["tip_box_location"]
    #     replacement_dict["tip_location"] = tip_box_location
    #     replacement_dict["x"] = ot2_patrick[tip_box_location][0]
    #     replacement_dict["y"] = ot2_patrick[tip_box_location][1]
    #     replacement_dict["z"] = ot2_patrick[tip_box_location][2]
    # elif payload["ot2_node"] == "ot2_spongebob":
    #     tip_box_location = payload["tip_box_location"]
    #     replacement_dict["tip_location"] = tip_box_location
    #     replacement_dict["x"] = ot2_spongebob[tip_box_location][0]
    #     replacement_dict["y"] = ot2_spongebob[tip_box_location][1]
    #     replacement_dict["z"] = ot2_spongebob[tip_box_location][2]
    # else:
    #     print("TESTING: unable to collect ot2 replacement variables")
    replacement_dict["combinations"] = payload["combinations"]
    replacement_dict["use_combinations"] = payload["use_combinations"]
    replacement_dict["non_combinatorial_sources"] = payload["non_combinatorial_sources"]
    # 3-round run: round-specific values ($round_num, $pcr_mm_start_well) and the starting tips of this run
    replacement_dict.update(payload.get("round_vars", {}))
    replacement_dict.update(payload.get("tip_starts", {}))
    return replacement_dict


def _as_value(x):
    return ast.literal_eval(x) if isinstance(x, str) else x


def combination_counts(payload: dict):
    """Return (number of combinations, columns they fill, total fragment transfers) for this round."""
    use = payload["use_combinations"]
    use = use if isinstance(use, bool) else str(use) != "False"
    if use:
        combos = list(itertools.product(*_as_value(payload["combinations"])))
    else:
        combos = _as_value(payload["non_combinatorial_sources"])
    n = len(combos)
    return n, (n + 7) // 8, sum(len(c) for c in combos)


class TipLedger:
    """Counts tips across Opentrons runs. Each run starts with fresh tip tracking on the robot, so
    full_run.py takes the start position here and passes it into the protocol ($..._tip_start).

    unit="column": 8-channel pickups, positions are columns across the racks in protocol order.
    unit="tip": single-tip pickups, positions are tips (order defined in the protocol).
    spares: full boxes waiting in Flex staging slots; swap() puts one in place of the current box.
    """

    def __init__(self, name, racks, unit="column", spares=0):
        self.name, self.racks, self.unit, self.spares = name, racks, unit, spares
        self.per_rack = 12 if unit == "column" else 96
        self.used = 0

    @property
    def capacity(self):
        return self.racks * self.per_rack

    def remaining(self):
        return self.capacity - self.used

    def needs_swap(self, n):
        return n > self.remaining() and self.spares > 0

    def swap(self):
        if self.spares <= 0:
            raise RuntimeError(f"{self.name}: no spare tip box left to swap in")
        self.spares -= 1
        self.used = 0

    def take(self, n):
        if n > self.remaining():
            raise RuntimeError(f"{self.name}: need {n} {self.unit}s but only {self.remaining()} left "
                               f"({self.spares} spare boxes). Refill before continuing.")
        start = self.used
        self.used += n
        return start


def write_timestamps_to_csv(
        csv_directory_path: str,
        experiment_id: str,
        bmg_filename: str,
        accurate_timestamp: str,
        resource_id: str,
    ):
    """Writes the more accurate timestamp data from each two plate
        substrate experiment to a file in the specified csv directory"""
    try:
        # format the file path
        csv_path = os.path.join(csv_directory_path, f"{experiment_id}.csv")

        # check if the file already exists
        already_exists = os.path.exists(csv_path)

        with open(csv_path, "a+") as f:
            csv_writer = csv.writer(f)

            # write header row if file was just created
            if not already_exists:
                csv_writer.writerow(["bmg filename", "utc timestamp", "resource id"])

            # write the data to the csv
            csv_writer.writerow([bmg_filename, accurate_timestamp, resource_id])


    except Exception as e:
        # DO NOT fail the experiment if data cannot write to csv file!
        print("Could not write bmg reading utc timestamp to file")
        print(e)



def calculate_total_combinations(combinations):
    """Calculate total number of combinations without generating them"""
    total = 1
    for sublist in combinations:
        total *= len(sublist)
    return total

def generate_all_combinations(combinations):
    """Generate all possible combinations from the jagged array"""
    return list(itertools.product(*combinations))



