"""CLI for managing PDF annotations via sidecar files."""

import argparse
import sys
from src.pdf_utils import (
    create_annotation,
    list_annotations,
    update_annotation,
    delete_annotation,
    render_overlays,
)


def cmd_add(args):
    """Add a new annotation and print its id."""
    pdf = args.pdf
    ann_id = create_annotation(
        pdf,
        {
            "page": args.page,
            "x": args.x,
            "y": args.y,
            "text": args.text,
            "size": args.size,
        },
    )
    print(ann_id)


def cmd_list(args):
    """List annotations for a PDF."""
    anns = list_annotations(args.pdf)
    for a in anns:
        print(a)


def cmd_edit(args):
    """Edit an annotation's properties."""
    props = {}
    if args.text:
        props["text"] = args.text
    if args.x is not None:
        props["x"] = args.x
    if args.y is not None:
        props["y"] = args.y
    if args.size is not None:
        props["size"] = args.size
    update_annotation(args.pdf, args.id, props)
    print("ok")


def cmd_remove(args):
    """Remove an annotation by id."""
    delete_annotation(args.pdf, args.id)
    print("ok")


def cmd_export(args):
    """Export the PDF with overlays to ``out``."""
    render_overlays(args.pdf, args.out, flatten=args.flatten)
    print(args.out)


def main():
    """Parse CLI arguments and dispatch commands."""
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add")
    a.add_argument("pdf")
    a.add_argument("--page", type=int, default=1)
    a.add_argument("--x", type=float, required=True)
    a.add_argument("--y", type=float, required=True)
    a.add_argument("--text", required=True)
    a.add_argument("--size", type=int, default=12)
    a.set_defaults(func=cmd_add)

    b = sub.add_parser("list")
    b.add_argument("pdf")
    b.set_defaults(func=cmd_list)

    c = sub.add_parser("edit")
    c.add_argument("pdf")
    c.add_argument("--id", required=True)
    c.add_argument("--text")
    c.add_argument("--x", type=float)
    c.add_argument("--y", type=float)
    c.add_argument("--size", type=int)
    c.set_defaults(func=cmd_edit)

    d = sub.add_parser("remove")
    d.add_argument("pdf")
    d.add_argument("--id", required=True)
    d.set_defaults(func=cmd_remove)

    e = sub.add_parser("export")
    e.add_argument("pdf")
    e.add_argument("out")
    e.add_argument("--flatten", action="store_true")
    e.set_defaults(func=cmd_export)

    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
