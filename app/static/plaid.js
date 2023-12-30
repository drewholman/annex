(async ($) => {
    // Check for existing item & ins_id combo
    const retrieveItemByPlaidInstitutionId = async (institution_id, user_id) => {
        const res = await fetch("/item/search");

    }
    // Grab a Link token to initialize Link
    const createLinkToken = async () => {
        // const res = await fetch("/create_link_token");
        const res = await fetch("/b_testing");
        const data = await res.json();
        const linkToken = data.link_token;
        localStorage.setItem("link_token", linkToken);
        return linkToken;
    };
    // Initialize Link
    const handler = Plaid.create({
        token: await createLinkToken(),
        onSuccess: async (publicToken, metadata) => {
            // Get linked institution
            console.log(metadata.institution.institution_id);
            const ins_id = metadata.institution.institution_id;
            // Check if this ins_id exists in current user query, if so return true
            const res = await fetch(`/cash/user/institution/${ins_id}`);
            const existing_institution = await res.json()
            console.log(existing_institution)
            if (existing_institution == "exists") {
                console.log(ins_id + ' has already been linked');
                window.scrollTo(0,0); 
                window.location.reload(); 
                return;
            }
            await fetch("/cash/set_access_token", {
                method: "POST",
                body: JSON.stringify({ public_token: publicToken }),
                headers: {
                    "Content-Type": "application/json",
                },
            });
            const item_id = await getBalance();
            syncTransactions(item_id);
        },
        onEvent: (eventName, metadata) => {
            console.log("Event:", eventName);
            console.log("Metadata:", metadata);
        },
        onExit: (error, metadata) => {
        console.log(error, metadata);
        if (metadata['status'] == 'requires_credentials') {
            // Stop loading.gif if plaid-link exited early
            const loader = document.querySelector('#loader');
            loader.style.display = 'none';
        }
        console.log(metadata['status'])
        },
    });

    // Start Link when button is clicked
    const linkAccountButton = document.getElementById("link-account");
    linkAccountButton.addEventListener("click", (event) => {
        const loader = document.querySelector('#loader');
        loader.style.display = 'block';
        handler.open();
    });
})(jQuery);

// Retrieves balance information
const getBalance = async function () {
    // const loader = document.querySelector('#loader');
    // loader.style.display = 'block';
    const response = await fetch("/cash/balance/get", {
        method: "GET",
    });
    const data = await response.json();
    const item_id = data.item.item_id;
    loader.style.display = 'none';
    location.reload();
    return item_id;
};

const syncTransactions = async function (item_id) {
    const response = await fetch(`/cash/item/${item_id}/transactions`, {
        method: "GET",
    });
    const data = await response.json();
    console.log(data);
};