import sys
from ast import dump, parse
from pathlib import Path


def main():
    input_path = sys.argv[1]
    print(input_path)
    source = read_file(Path(input_path))
    syntax_tree = parse(source, filename=input_path)
    print(dump(syntax_tree, indent=2))


def read_file(file_path: Path) -> str:
    with file_path.open(encoding="utf-8", newline=None) as f:
        return f.read()


if __name__ == "__main__":
    main()
