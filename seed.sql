INSERT INTO menu_categories (name, sort_order) VALUES ('Starters', 1);
INSERT INTO menu_categories (name, sort_order) VALUES ('Mains', 2);
INSERT INTO menu_categories (name, sort_order) VALUES ('Desserts', 3);
INSERT INTO menu_categories (name, sort_order) VALUES ('Drinks', 4);

INSERT INTO menu_items (category_id, name, description, price_cents, available) VALUES
(1, 'Bruschetta', 'Toasted bread with tomato and basil', 895, 1),
(1, 'Soup of the Day', 'Chef''s seasonal soup', 650, 1),
(2, 'Grilled Salmon', 'Atlantic salmon with seasonal vegetables', 1895, 1),
(2, 'Ribeye Steak', '300g ribeye with fries and salad', 2495, 1),
(2, 'Pasta Primavera', 'Seasonal vegetables in garlic sauce', 1395, 1),
(3, 'Tiramisu', 'Classic Italian coffee dessert', 995, 1),
(3, 'Cheese Plate', 'Selection of artisan cheeses', 1295, 0),
(4, 'Sparkling Water', '750ml bottle', 395, 1),
(4, 'House Red Wine', 'Glass of Merlot', 795, 1);

INSERT INTO dining_tables (label, seats, active) VALUES ('T1', 2, 1);
INSERT INTO dining_tables (label, seats, active) VALUES ('T2', 4, 1);
INSERT INTO dining_tables (label, seats, active) VALUES ('T3', 6, 1);
INSERT INTO dining_tables (label, seats, active) VALUES ('T4', 8, 1);
INSERT INTO dining_tables (label, seats, active) VALUES ('T5', 4, 0);
