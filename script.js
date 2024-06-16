// Add this script in a <script> tag before the closing </body> tag

document.addEventListener('DOMContentLoaded', (event) => {
    const dropdown = document.querySelector('.dropdown');
    dropdown.addEventListener('mouseenter', () => {
        const dropdownContent = dropdown.querySelector('.dropdown-content');
        dropdownContent.style.display = 'block';
        setTimeout(() => {
            dropdownContent.style.opacity = '1';
        }, 0);
    });
    dropdown.addEventListener('mouseleave', () => {
        const dropdownContent = dropdown.querySelector('.dropdown-content');
        dropdownContent.style.opacity = '0';
        setTimeout(() => {
            dropdownContent.style.display = 'none';
        }, 300); // Match this duration with the CSS transition duration
    });
});
