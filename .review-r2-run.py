from pathlib import Path
source = Path('.review-versioned-temp.py').read_text()
# Windows drive paths must be converted for the explicitly selected Git Bash.
source = source.replace(".as_posix()", ".as_posix().replace('P:', '/p')")
exec(compile(source, '.review-versioned-temp.py (Git Bash path conversion)', 'exec'))
