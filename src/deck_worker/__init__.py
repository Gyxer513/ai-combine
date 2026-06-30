"""Deck-worker: autonomous execution of tasks from Nextcloud Deck.

Polls the board, takes cards from To Do, routes each by label to the right agent,
runs it via the orchestrator, writes the result as a comment, and moves it to Done.
"""
