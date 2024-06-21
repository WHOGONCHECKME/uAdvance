/*
document.addEventListener('DOMContentLoaded', (event) => {
    const dropdown = document.querySelector('.dropdown');
    if (dropdown) {
        console.log("Dropdown element found");
        dropdown.addEventListener('mouseenter', () => {
            console.log("Mouse entered dropdown");
            const dropdownContent = dropdown.querySelector('.dropdown-content');
            if (dropdownContent) {
                dropdownContent.style.display = 'block';
                setTimeout(() => {
                    dropdownContent.style.opacity = '1';
                    dropdownContent.style.visibility = 'visible';
                }, 0);
            } else {
                console.log("Dropdown content not found");
            }
        });
        dropdown.addEventListener('mouseleave', () => {
            console.log("Mouse left dropdown");
            const dropdownContent = dropdown.querySelector('.dropdown-content');
            if (dropdownContent) {
                dropdownContent.style.opacity = '0';
                dropdownContent.style.visibility = 'hidden';
                setTimeout(() => {
                    dropdownContent.style.display = 'none';
                }, 300);
            } else {
                console.log("Dropdown content not found");
            }
        });
    } else {
        console.log("Dropdown element not found");
    }
});
*/