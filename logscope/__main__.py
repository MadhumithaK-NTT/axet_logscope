"""Allow ``python -m logscope`` to invoke the CLI."""

from logscope.cli import main
import sys

sys.exit(main())
