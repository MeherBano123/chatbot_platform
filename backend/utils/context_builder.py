# utils/context_builder.py

def build_context(search_results, max_length=4000):
    context_parts = []
    current_len = 0

    for i, r in enumerate(search_results, 1):
        heading = r.get("heading", "")
        sub_heading = r.get("sub_heading", "")
        metadata = r.get("meta_data", "")
        content = r.get("chunk_text", "")
        similarity = float(r.get("similarity", 0))

        block = f"""
[Document {i}]
Heading: {heading}
Subheading: {sub_heading}
Metadata: {metadata}
Relevance Score: {similarity:.3f}

Content:
{content}
"""

        if current_len + len(block) > max_length:
            break

        context_parts.append(block.strip())
        current_len += len(block)

    return "\n\n".join(context_parts)