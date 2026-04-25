import streamlit as st

from agent import Agent


st.set_page_config(page_title="Payment Collection Agent", page_icon="💳", layout="centered")


def reset_session() -> None:
    st.session_state.agent = Agent()
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Welcome. Please enter your account ID to begin the payment collection flow.",
        }
    ]


if "agent" not in st.session_state or "messages" not in st.session_state:
    reset_session()


st.title("Payment Collection Agent")
st.caption("A simple chat UI for the payment collection flow.")

col1, col2 = st.columns([3, 1])
with col1:
    st.write("Verify the account, confirm identity, and collect payment details in a guided flow.")
with col2:
    if st.button("Start Over", use_container_width=True):
        reset_session()
        st.rerun()

with st.expander("How to use", expanded=False):
    st.markdown(
        "\n".join(
            [
                "- Start by entering the account ID, for example `ACC1001`.",
                "- Then follow the prompts for full name, verification, amount, and card details.",
                "- Type one message at a time, just like the CLI version.",
            ]
        )
    )

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Type your message")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    reply = st.session_state.agent.next(user_input)["message"]
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)
