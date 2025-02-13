drop table if exists user;
create table user (
  user_id integer primary key autoincrement,
  username string not null,
  email string not null,
  pw_hash string not null
);

drop table if exists follower;
create table follower (
  who_id integer,
  whom_id integer
);

drop table if exists message;
create table message (
  message_id integer primary key autoincrement,
  author_id integer not null,
  text string not null,
  pub_date integer,
  flagged integer
);

-- TODO these might be required for the "latest" api calls? 
 /*
create table latest (
  id integer primary key,
  value integer
);

-- Copilot suggested this, but I'm not sure if it's necessary
insert into latest (id, value) VALUES (1, 0);
*/